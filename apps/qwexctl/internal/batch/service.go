package batch

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"time"

	"github.com/Quatton/qwex/apps/qwexctl/internal/connect"
	"github.com/Quatton/qwex/apps/qwexctl/internal/pods"
	"github.com/google/uuid"
	v1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/util/wait"
)

const DemoImage = "ghcr.io/astral-sh/uv:0.9.13-python3.12-bookworm"

const BatchWorkDir = "/batch"
const BatchContainerName = "batchcontainer"
const InitContainerName = pods.InitContainerName
const BatchVolumeName = "batch"

type Service struct {
	connector *connect.Service
	Image     string
	Command   []string
	Args      []string
	WorkDir   string
	Name      string
}

func NewService(connector *connect.Service, sha, image string, command []string, args []string, workDir string, _name string) *Service {
	name := "job"
	if _name != "" {
		name = _name
	}
	return &Service{
		connector: connector,
		Image:     image,
		Command:   command,
		Args:      args,
		WorkDir:   workDir,
		Name:      name,
	}
}

func shortSha(sha string) string {
	if len(sha) >= 7 {
		return sha[:7]
	}
	return sha
}

func generateRunID(job string) string {
	timestamp := time.Now().UTC().Format("20060102-150405")
	uuidPart := uuid.New().String()[:8]
	return fmt.Sprintf("%s-%s-%s", job, timestamp, uuidPart)
}

func (s *Service) buildBatchJobSpec(sha string) (*v1.Job, error) {
	runID := generateRunID(s.Name)
	ttl := int32(300)        // 5 minutes
	backoffLimit := int32(0) // Don't retry on failure
	job := &v1.Job{
		ObjectMeta: metav1.ObjectMeta{
			GenerateName: fmt.Sprintf("%s-", s.Name),
			Namespace:    s.connector.Namespace,
			Labels: map[string]string{
				"qwex.dev/type":   "batch",
				"qwex.dev/sha":    sha,
				"qwex.dev/run-id": runID,
			},
		},
		Spec: v1.JobSpec{
			TTLSecondsAfterFinished: &ttl,
			BackoffLimit:            &backoffLimit,
			Completions:             nil,
			Parallelism:             nil,
			Template: corev1.PodTemplateSpec{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{
						"qwex.dev/type":   "batch",
						"qwex.dev/sha":    sha,
						"qwex.dev/run-id": runID,
					},
				},
				Spec: corev1.PodSpec{
					RestartPolicy: corev1.RestartPolicyNever,
					Volumes: []corev1.Volume{
						{
							Name: pods.WorkspaceVolumeName,
							VolumeSource: corev1.VolumeSource{
								PersistentVolumeClaim: &corev1.PersistentVolumeClaimVolumeSource{
									ClaimName: pods.MakePVCName(s.connector.Namespace),
								},
							},
						},
						{
							Name: BatchVolumeName,
							VolumeSource: corev1.VolumeSource{
								EmptyDir: &corev1.EmptyDirVolumeSource{},
							},
						},
						{
							Name: pods.CacheVolumeName,
							VolumeSource: corev1.VolumeSource{
								PersistentVolumeClaim: &corev1.PersistentVolumeClaimVolumeSource{
									ClaimName: pods.MakeCachePVCName(s.connector.Namespace),
								},
							},
						},
					},
					InitContainers: []corev1.Container{
						{
							Name:    InitContainerName,
							Image:   pods.SyncImage,
							Command: []string{"/bin/sh", "-c"},
							Args: []string{
								fmt.Sprintf(
									"git --git-dir=%s/.git archive --format=tar %s | tar -x -C %s",
									pods.WorkspaceMountPath,
									sha,
									BatchWorkDir,
								),
							},
							WorkingDir: s.WorkDir,
							VolumeMounts: []corev1.VolumeMount{
								{
									Name:      pods.WorkspaceVolumeName,
									MountPath: pods.WorkspaceMountPath,
								},
								{
									Name:      BatchVolumeName,
									MountPath: BatchWorkDir,
								},
							},
						},
					},
					Containers: []corev1.Container{
						{
							Name:       BatchContainerName,
							Image:      s.Image,
							Command:    s.Command,
							Args:       s.Args,
							WorkingDir: BatchWorkDir,
							VolumeMounts: []corev1.VolumeMount{
								{
									Name:      pods.WorkspaceVolumeName,
									MountPath: pods.WorkspaceMountPath,
								},
								{
									Name:      BatchVolumeName,
									MountPath: BatchWorkDir,
								},
								{
									Name:      pods.CacheVolumeName,
									MountPath: pods.CacheMountPath,
								},
							},
							Resources: corev1.ResourceRequirements{
								Requests: corev1.ResourceList{
									corev1.ResourceCPU:    resource.MustParse("2000m"),
									corev1.ResourceMemory: resource.MustParse("4Gi"),
								},
								Limits: corev1.ResourceList{
									corev1.ResourceCPU:    resource.MustParse("2000m"),
									corev1.ResourceMemory: resource.MustParse("8Gi"),
								},
							},
							Env: []corev1.EnvVar{
								{
									Name:  "XDG_CACHE_HOME",
									Value: pods.CacheMountPath,
								},
							},
						},
					},
				},
			},
		},
	}
	return job, nil

}

func (s *Service) EnsureSyncAndSubmitJob(ctx context.Context) (*v1.Job, error) {
	clean, err := s.connector.IsLocalStatusClean(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to check sync status: %w", err)
	}

	if !clean {
		return nil, fmt.Errorf("local changes detected; please commit or stash changes before submitting a batch job")
	}

	err = s.connector.SyncOnce(ctx)

	if err != nil && err.Error() != "up_to_date" {
		return nil, fmt.Errorf("failed to sync before submitting job: %w", err)
	}

	remoteHead, err := s.connector.GetRemoteHead(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get remote head after sync: %w", err)
	}

	jobSpec, err := s.buildBatchJobSpec(remoteHead.CommitHash)
	if err != nil {
		return nil, fmt.Errorf("failed to build batch job spec: %w", err)
	}

	jobsClient := s.connector.Client.BatchV1().Jobs(s.connector.Namespace)
	job, err := jobsClient.Create(ctx, jobSpec, metav1.CreateOptions{})
	if err != nil {
		return nil, fmt.Errorf("failed to create batch job: %w", err)
	}

	return job, nil
}

func (s *Service) WaitForRunReady(ctx context.Context, runID string, timeout time.Duration) (string, error) {
	interval := 2 * time.Second
	var pod *corev1.Pod
	err := wait.PollUntilContextTimeout(ctx, interval, timeout, true, func(ctx context.Context) (bool, error) {
		podList, err := s.connector.Client.CoreV1().Pods(s.connector.Namespace).List(ctx, metav1.ListOptions{
			LabelSelector: fmt.Sprintf("qwex.dev/run-id=%s", runID),
		})
		if err != nil {
			return false, err
		}
		if len(podList.Items) == 0 {
			return false, nil
		}

		pod = &podList.Items[0]

		if pod.Status.Phase == corev1.PodFailed {
			return true, nil
		}

		if pod.Status.Phase == corev1.PodSucceeded {
			return true, nil
		}

		if pod.Status.Phase == corev1.PodRunning {
			for _, containerStatus := range pod.Status.ContainerStatuses {
				if containerStatus.Name == BatchContainerName {
					if containerStatus.State.Running != nil {
						return true, nil
					}
					if containerStatus.State.Terminated != nil {
						return true, nil
					}
					if containerStatus.State.Waiting != nil {
						return false, nil
					}
				}
			}
			return false, nil
		}

		return false, nil
	})

	if err != nil {
		return "", err
	}

	return pod.Name, nil
}

func (s *Service) FollowRunLogs(ctx context.Context, runID string, writer io.Writer) error {
	podName, err := s.WaitForRunReady(ctx, runID, 2*time.Minute)
	if err != nil {
		return fmt.Errorf("error waiting for pod to be running: %w", err)
	}

	return s.streamLogsFromPod(ctx, podName, writer, true)
}

func (s *Service) GetRunLogs(ctx context.Context, runID string) (string, error) {
	podName, err := s.WaitForRunReady(ctx, runID, 2*time.Minute)
	if err != nil {
		return "", fmt.Errorf("error waiting for pod to be running: %w", err)
	}

	var buf bytes.Buffer
	err = s.streamLogsFromPod(ctx, podName, &buf, false)
	if err != nil {
		return "", err
	}
	return buf.String(), nil
}

type bytesWriter struct {
	buf *[]byte
}

func (w *bytesWriter) Write(p []byte) (n int, err error) {
	*w.buf = append(*w.buf, p...)
	return len(p), nil
}

func (s *Service) streamLogsFromPod(ctx context.Context, podName string, writer io.Writer, follow bool) error {
	client := s.connector.Client

	logOptions := &corev1.PodLogOptions{
		Container: BatchContainerName,
		Follow:    follow,
	}

	req := client.CoreV1().Pods(s.connector.Namespace).GetLogs(podName, logOptions)
	stream, err := req.Stream(ctx)
	if err != nil {
		return fmt.Errorf("error opening log stream: %w", err)
	}
	defer stream.Close()

	_, err = io.Copy(writer, stream)
	if err != nil && err != io.EOF {
		return fmt.Errorf("error reading logs: %w", err)
	}

	return nil
}
