package runner

import (
	"context"
	"time"
)

// JobSpec defines the template/configuration for a job
type JobSpec struct {
	ID         string            // Optional: custom job ID
	Name       string            // Human-readable name
	Command    string            // Command to execute (e.g., "python")
	Args       []string          // Command arguments (e.g., ["main.py", "--epochs", "10"])
	Env        map[string]string // Environment variables
	WorkingDir string            // Working directory (defaults to cwd)
	CommitHash string            // Optional: git commit hash
	RepoURL    string            // Optional: repository URL
}

// RunStatus represents the current state of a run
type RunStatus string

const (
	RunStatusPending    RunStatus = "PENDING"    // Queued, not yet started
	RunStatusInitiating RunStatus = "INITIATING" // Setting up environment
	RunStatusRunning    RunStatus = "RUNNING"    // Currently executing
	RunStatusSucceeded  RunStatus = "SUCCEEDED"  // Completed successfully (exit code 0)
	RunStatusFailed     RunStatus = "FAILED"     // Completed with error (exit code != 0)
	RunStatusCancelled  RunStatus = "CANCELLED"  // Cancelled by user
)

// Run represents a specific execution instance of a job
type Run struct {
	ID         string            `json:"id"`
	JobID      string            `json:"job_id"`
	Status     RunStatus         `json:"status"`
	Command    string            `json:"command"`
	Args       []string          `json:"args"`
	Env        map[string]string `json:"env,omitempty"`
	CreatedAt  time.Time         `json:"created_at"`
	StartedAt  *time.Time        `json:"started_at,omitempty"`
	FinishedAt *time.Time        `json:"finished_at,omitempty"`
	ExitCode   *int              `json:"exit_code,omitempty"`
	Error      string            `json:"error,omitempty"`
	RunDir     string            `json:"run_dir"`
	LogsPath   string            `json:"logs_path"`
	Metadata   map[string]string `json:"metadata,omitempty"`
}

// Runner is the execution engine interface
type Runner interface {
	// Submit creates a new run and starts execution
	// Returns the Run object with initial state (PENDING or RUNNING)
	Submit(ctx context.Context, spec JobSpec) (*Run, error)

	// Wait blocks until the run completes or context is cancelled
	// Returns the final Run state
	Wait(ctx context.Context, runID string) (*Run, error)

	// GetRun fetches the current state of a run
	GetRun(ctx context.Context, runID string) (*Run, error)

	// Cancel attempts to cancel a running job
	Cancel(ctx context.Context, runID string) error

	// ListRuns returns all runs, optionally filtered by status
	ListRuns(ctx context.Context, status *RunStatus) ([]*Run, error)
}
