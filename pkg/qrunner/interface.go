package qrunner

import (
	"context"
	"time"
)

// RunStatus represents the execution state of a run
type RunStatus string

const (
	RunStatusPending   RunStatus = "pending"
	RunStatusRunning   RunStatus = "running"
	RunStatusSucceeded RunStatus = "succeeded"
	RunStatusFailed    RunStatus = "failed"
	RunStatusCancelled RunStatus = "cancelled"
)

// JobSpec defines the specification for a job to be run
type JobSpec struct {
	ID         string            // Optional: if empty, a new ID will be generated
	Name       string            // Human-readable name for the job
	Command    string            // Command to execute
	Args       []string          // Command arguments
	Env        map[string]string // Environment variables
	WorkingDir string            // Working directory for execution
}

// Run represents an execution of a job
type Run struct {
	ID         string            `json:"id"`
	JobID      string            `json:"job_id"`
	Status     RunStatus         `json:"status"`
	Command    string            `json:"command"`
	Args       []string          `json:"args,omitempty"`
	Env        map[string]string `json:"env,omitempty"`
	WorkingDir string            `json:"working_dir,omitempty"`
	CreatedAt  time.Time         `json:"created_at"`
	StartedAt  *time.Time        `json:"started_at,omitempty"`
	FinishedAt *time.Time        `json:"finished_at,omitempty"`
	ExitCode   *int              `json:"exit_code,omitempty"`
	Error      string            `json:"error,omitempty"`
	RunDir     string            `json:"run_dir"`
	LogsPath   string            `json:"logs_path"`
	Metadata   map[string]string `json:"metadata,omitempty"`
}

// Runner defines the interface for executing jobs
type Runner interface {
	// Submit submits a new job for execution
	Submit(ctx context.Context, spec JobSpec) (*Run, error)

	// Wait waits for a run to complete
	Wait(ctx context.Context, runID string) (*Run, error)

	// GetRun retrieves the status of a run
	GetRun(ctx context.Context, runID string) (*Run, error)

	// Cancel cancels a running job
	Cancel(ctx context.Context, runID string) error

	// ListRuns lists all runs, optionally filtered by status
	ListRuns(ctx context.Context, status *RunStatus) ([]*Run, error)
}
