package runner

import "context"

type JobSpec struct {
	Name       string
	Command    string
	CommitHash string
	RepoURL    string
	Env        map[string]string
}

type RunStatus string

const (
	RunStatusPending      RunStatus = "PENDING"
	RunStatusInitializing RunStatus = "INITIALIZING"
	RunStatusRunning      RunStatus = "RUNNING"
	RunStatusSucceeded    RunStatus = "SUCCEEDED"
	RunStatusFailed       RunStatus = "FAILED"
	RunStatusCancelled    RunStatus = "CANCELLED"
	RunStatusTimeout      RunStatus = "TIMEOUT"
	RunStatusFinalizing   RunStatus = "FINALIZING"
)

type RunIteration struct {
	CreatedAt int64
	Status    RunStatus
}

type Run struct {
	ID         string
	JobID      string
	Iterations []RunIteration
}

type Runner interface {
	Submit(ctx context.Context, spec JobSpec) (*Run, error)
	GetRunStatus(ctx context.Context, runID string) (*Run, error)
}
