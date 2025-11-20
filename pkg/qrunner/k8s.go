package qrunner

import (
	"context"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/quatton/qwex/pkg/k8s"
	"github.com/quatton/qwex/pkg/qapi/services/jobs"
	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/utils/ptr"
)

// K8sRunner executes runs as Kubernetes Jobs with Kueue integration
type K8sRunner struct {
	jobManager *jobs.JobManager
	namespace  string
	queueName  string
	image      string
}

// NewK8sRunner creates a new Kubernetes runner
func NewK8sRunner(namespace, queueName, image string) (*K8sRunner, error) {
	client, err := k8s.NewClient()
	if err != nil {
		return nil, fmt.Errorf("creating k8s client: %w", err)
	}

	return &K8sRunner{
		jobManager: jobs.NewJobManager(client, namespace),
		namespace:  namespace,
		queueName:  queueName,
		image:      image,
	}, nil
}

// Submit creates and submits a Kubernetes Job
func (r *K8sRunner) Submit(ctx context.Context, spec JobSpec) (*Run, error) {
	runID := uuid.New().String()
	if spec.ID != "" {
		runID = spec.ID
	}

	jobName := fmt.Sprintf("qwex-%s", runID[:8])

	// Build the Job spec
	job := &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{
			Name: jobName,
			Labels: map[string]string{
				jobs.KueueQueueLabel: r.queueName,
				"qwex.run-id":        runID,
			},
		},
		Spec: batchv1.JobSpec{
			Parallelism:  ptr.To(int32(1)),
			Completions:  ptr.To(int32(1)),
			Suspend:      ptr.To(true), // Start suspended, Kueue will unsuspend
			BackoffLimit: ptr.To(int32(0)),
			Template: corev1.PodTemplateSpec{
				Spec: corev1.PodSpec{
					RestartPolicy: corev1.RestartPolicyNever,
					Containers: []corev1.Container{
						{
							Name:    "main",
							Image:   r.image,
							Command: append([]string{spec.Command}, spec.Args...),
							Env:     envMapToEnvVars(spec.Env),
							Resources: corev1.ResourceRequirements{
								Requests: corev1.ResourceList{
									corev1.ResourceCPU:    mustParseQuantity("100m"),
									corev1.ResourceMemory: mustParseQuantity("128Mi"),
								},
							},
						},
					},
				},
			},
		},
	}

	// Create the job
	createdJob, err := r.jobManager.CreateJob(ctx, job)
	if err != nil {
		return nil, fmt.Errorf("creating job: %w", err)
	}

	now := time.Now()
	run := &Run{
		ID:        runID,
		JobID:     spec.Name,
		Status:    RunStatusPending,
		Command:   spec.Command,
		Args:      spec.Args,
		Env:       spec.Env,
		CreatedAt: now,
		Metadata: map[string]string{
			"k8s_job_name":  createdJob.Name,
			"k8s_namespace": r.namespace,
		},
	}

	return run, nil
}

// Wait waits for a job to complete
func (r *K8sRunner) Wait(ctx context.Context, runID string) (*Run, error) {
	run, err := r.GetRun(ctx, runID)
	if err != nil {
		return nil, err
	}

	jobName := run.Metadata["k8s_job_name"]
	if jobName == "" {
		return nil, fmt.Errorf("job name not found in run metadata")
	}

	// Poll until complete
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-ticker.C:
			run, err := r.GetRun(ctx, runID)
			if err != nil {
				return nil, err
			}
			if run.Status == RunStatusSucceeded || run.Status == RunStatusFailed || run.Status == RunStatusCancelled {
				return run, nil
			}
		}
	}
}

// GetRun fetches the current state of a run
func (r *K8sRunner) GetRun(ctx context.Context, runID string) (*Run, error) {
	// List jobs with this run ID
	jobs, err := r.jobManager.ListJobs(ctx, fmt.Sprintf("qwex.run-id=%s", runID))
	if err != nil {
		return nil, fmt.Errorf("listing jobs: %w", err)
	}

	if len(jobs.Items) == 0 {
		return nil, fmt.Errorf("run %s not found", runID)
	}

	job := &jobs.Items[0]

	// Convert job status to run status
	run := &Run{
		ID:        runID,
		Status:    jobStatusToRunStatus(job),
		CreatedAt: job.CreationTimestamp.Time,
		Metadata: map[string]string{
			"k8s_job_name":  job.Name,
			"k8s_namespace": r.namespace,
		},
	}

	// Set start/finish times based on job conditions
	for _, condition := range job.Status.Conditions {
		if condition.Type == batchv1.JobComplete && condition.Status == corev1.ConditionTrue {
			run.FinishedAt = &condition.LastTransitionTime.Time
		}
		if condition.Type == batchv1.JobFailed && condition.Status == corev1.ConditionTrue {
			run.FinishedAt = &condition.LastTransitionTime.Time
			run.Error = condition.Message
		}
	}

	// Get pod for more details
	pods, err := r.jobManager.GetJobPods(ctx, job.Name)
	if err == nil && len(pods.Items) > 0 {
		pod := &pods.Items[0]
		if pod.Status.StartTime != nil {
			run.StartedAt = &pod.Status.StartTime.Time
		}


	// Get exit code from container status
	for _, status := range pod.Status.ContainerStatuses {
		if status.State.Terminated != nil {
			exitCode := int(status.State.Terminated.ExitCode)
			run.ExitCode = &exitCode
		}
	}

	run.Metadata["logs_path"] = fmt.Sprintf("pod/%s", pod.Name)
}

return run, nil
}// Cancel cancels a running job
func (r *K8sRunner) Cancel(ctx context.Context, runID string) error {
	run, err := r.GetRun(ctx, runID)
	if err != nil {
		return err
	}

	jobName := run.Metadata["k8s_job_name"]
	if jobName == "" {
		return fmt.Errorf("job name not found in run metadata")
	}

	return r.jobManager.DeleteJob(ctx, jobName)
}

// ListRuns lists all runs, optionally filtered by status
func (r *K8sRunner) ListRuns(ctx context.Context, status *RunStatus) ([]*Run, error) {
	jobs, err := r.jobManager.ListJobs(ctx, "")
	if err != nil {
		return nil, fmt.Errorf("listing jobs: %w", err)
	}

	var runs []*Run
	for _, job := range jobs.Items {
		runID := job.Labels["qwex.run-id"]
		if runID == "" {
			continue
		}

		run, err := r.GetRun(ctx, runID)
		if err != nil {
			continue
		}

		// Filter by status if specified
		if status != nil && run.Status != *status {
			continue
		}

		runs = append(runs, run)
	}

	return runs, nil
}

// Helper functions

func envMapToEnvVars(envMap map[string]string) []corev1.EnvVar {
	if envMap == nil {
		return nil
	}

	envVars := make([]corev1.EnvVar, 0, len(envMap))
	for k, v := range envMap {
		envVars = append(envVars, corev1.EnvVar{
			Name:  k,
			Value: v,
		})
	}
	return envVars
}

func mustParseQuantity(s string) resource.Quantity {
	q, err := resource.ParseQuantity(s)
	if err != nil {
		panic(fmt.Sprintf("invalid quantity %q: %v", s, err))
	}
	return q
}

func jobStatusToRunStatus(job *batchv1.Job) RunStatus {
	// Check if job is suspended (pending)
	if job.Spec.Suspend != nil && *job.Spec.Suspend {
		return RunStatusPending
	}

	// Check job conditions
	for _, condition := range job.Status.Conditions {
		if condition.Type == batchv1.JobComplete && condition.Status == corev1.ConditionTrue {
			return RunStatusSucceeded
		}
		if condition.Type == batchv1.JobFailed && condition.Status == corev1.ConditionTrue {
			return RunStatusFailed
		}
	}

	// If active, it's running
	if job.Status.Active > 0 {
		return RunStatusRunning
	}

	// Default to pending
	return RunStatusPending
}
