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
	ID         string            // Unique run ID
	JobID      string            // Reference to job ID
	Status     RunStatus         // Current status
	Command    string            // Full command executed
	Args       []string          // Command arguments
	Env        map[string]string // Environment variables used
	CreatedAt  time.Time         // When the run was created
	StartedAt  *time.Time        // When execution started (nil if not started)
	FinishedAt *time.Time        // When execution finished (nil if not finished)
	ExitCode   *int              // Process exit code (nil if not finished)
	Error      string            // Error message (if failed)
	RunDir     string            // Path to .qwex/runs/<run-id>
	LogsPath   string            // Path to stdout.log
	Metadata   map[string]string // Additional metadata
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
