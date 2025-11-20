package jobs

import (
	"context"
	"fmt"

	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
)

const (
	// KueueQueueLabel is the label key for Kueue queue name
	KueueQueueLabel = "kueue.x-k8s.io/queue-name"
)

// JobManager handles Kubernetes Job operations
type JobManager struct {
	client    *kubernetes.Clientset
	namespace string
}

// NewJobManager creates a new JobManager
func NewJobManager(client *kubernetes.Clientset, namespace string) *JobManager {
	return &JobManager{
		client:    client,
		namespace: namespace,
	}
}

// CreateJob creates a new Kubernetes Job
func (jm *JobManager) CreateJob(ctx context.Context, job *batchv1.Job) (*batchv1.Job, error) {
	return jm.client.BatchV1().Jobs(jm.namespace).Create(ctx, job, metav1.CreateOptions{})
}

// GetJob retrieves a Job by name
func (jm *JobManager) GetJob(ctx context.Context, name string) (*batchv1.Job, error) {
	return jm.client.BatchV1().Jobs(jm.namespace).Get(ctx, name, metav1.GetOptions{})
}

// DeleteJob deletes a Job by name
func (jm *JobManager) DeleteJob(ctx context.Context, name string) error {
	deletePolicy := metav1.DeletePropagationForeground
	return jm.client.BatchV1().Jobs(jm.namespace).Delete(ctx, name, metav1.DeleteOptions{
		PropagationPolicy: &deletePolicy,
	})
}

// ListJobs lists all Jobs in the namespace
func (jm *JobManager) ListJobs(ctx context.Context, labelSelector string) (*batchv1.JobList, error) {
	return jm.client.BatchV1().Jobs(jm.namespace).List(ctx, metav1.ListOptions{
		LabelSelector: labelSelector,
	})
}

// GetPodLogs retrieves logs from a pod
func (jm *JobManager) GetPodLogs(ctx context.Context, podName string) (string, error) {
	req := jm.client.CoreV1().Pods(jm.namespace).GetLogs(podName, &corev1.PodLogOptions{})
	logs, err := req.Stream(ctx)
	if err != nil {
		return "", fmt.Errorf("getting pod logs: %w", err)
	}
	defer logs.Close()

	buf := new([]byte)
	*buf = make([]byte, 0, 1024*1024) // 1MB buffer
	n, err := logs.Read(*buf)
	if err != nil && err.Error() != "EOF" {
		return "", fmt.Errorf("reading pod logs: %w", err)
	}

	return string((*buf)[:n]), nil
}

// GetJobPods returns all pods for a given job
func (jm *JobManager) GetJobPods(ctx context.Context, jobName string) (*corev1.PodList, error) {
	return jm.client.CoreV1().Pods(jm.namespace).List(ctx, metav1.ListOptions{
		LabelSelector: fmt.Sprintf("job-name=%s", jobName),
	})
}
