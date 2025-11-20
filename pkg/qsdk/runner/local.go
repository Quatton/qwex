package runner

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/quatton/qwex/pkg/qsdk"
)

type LocalRunner struct {
	runsDir string
	mu      sync.RWMutex
	runs    map[string]*runProcess // in-memory tracking of active runs
}

// runProcess tracks an active process
type runProcess struct {
	cmd    *exec.Cmd
	run    *Run
	cancel context.CancelFunc
}

func NewLocalRunner() *LocalRunner {
	cwd, _ := os.Getwd()
	return &LocalRunner{
		runsDir: filepath.Join(cwd, qsdk.ConfigRoot, "runs"),
		runs:    make(map[string]*runProcess),
	}
}

func (r *LocalRunner) Submit(ctx context.Context, spec JobSpec) (*Run, error) {
	// Generate run ID
	runID := uuid.New().String()
	if spec.ID != "" {
		runID = spec.ID
	}

	// Create run directory
	runDir := filepath.Join(r.runsDir, runID)
	if err := os.MkdirAll(runDir, 0o755); err != nil {
		return nil, fmt.Errorf("failed to create run directory: %w", err)
	}

	// Create logs directory
	logsPath := filepath.Join(runDir, "stdout.log")

	// Initialize run object
	now := time.Now()
	run := &Run{
		ID:        runID,
		JobID:     spec.Name,
		Status:    RunStatusPending,
		Command:   spec.Command,
		Args:      spec.Args,
		Env:       spec.Env,
		CreatedAt: now,
		RunDir:    runDir,
		LogsPath:  logsPath,
		Metadata:  make(map[string]string),
	}

	// Save initial state
	if err := r.saveRun(run); err != nil {
		return nil, fmt.Errorf("failed to save run state: %w", err)
	}

	// Start execution in background
	go r.executeRun(ctx, run, spec)

	return run, nil
}

func (r *LocalRunner) executeRun(ctx context.Context, run *Run, spec JobSpec) {
	// Update status to RUNNING
	now := time.Now()
	run.StartedAt = &now
	run.Status = RunStatusRunning
	r.saveRun(run)

	// Create cancellable context
	execCtx, cancel := context.WithCancel(ctx)
	defer cancel()

	// Build command
	cmd := exec.CommandContext(execCtx, spec.Command, spec.Args...)

	// Set working directory
	if spec.WorkingDir != "" {
		cmd.Dir = spec.WorkingDir
	} else {
		cwd, _ := os.Getwd()
		cmd.Dir = cwd
	}

	// Set environment variables
	cmd.Env = os.Environ()
	for k, v := range spec.Env {
		cmd.Env = append(cmd.Env, fmt.Sprintf("%s=%s", k, v))
	}
	// Add qwex-specific env vars
	cmd.Env = append(cmd.Env,
		fmt.Sprintf("QWEX_RUN_ID=%s", run.ID),
		fmt.Sprintf("QWEX_RUN_DIR=%s", run.RunDir),
	)

	// Create log file
	logFile, err := os.Create(run.LogsPath)
	if err != nil {
		r.finishRunWithError(run, fmt.Errorf("failed to create log file: %w", err))
		return
	}
	defer logFile.Close()

	// Redirect stdout and stderr to log file
	cmd.Stdout = logFile
	cmd.Stderr = logFile

	// Track the process
	r.mu.Lock()
	r.runs[run.ID] = &runProcess{
		cmd:    cmd,
		run:    run,
		cancel: cancel,
	}
	r.mu.Unlock()

	// Execute command
	err = cmd.Run()

	// Clean up from tracking
	r.mu.Lock()
	delete(r.runs, run.ID)
	r.mu.Unlock()

	// Determine final status
	finishTime := time.Now()
	run.FinishedAt = &finishTime

	if err != nil {
		// Check if context was cancelled first
		if execCtx.Err() == context.Canceled {
			// Process was cancelled
			run.Status = RunStatusCancelled
			run.Error = "run was cancelled"
		} else if exitErr, ok := err.(*exec.ExitError); ok {
			// Process exited with non-zero code
			exitCode := exitErr.ExitCode()
			run.ExitCode = &exitCode
			run.Status = RunStatusFailed
			run.Error = fmt.Sprintf("process exited with code %d", exitCode)
		} else {
			// Other error (failed to start, etc.)
			run.Status = RunStatusFailed
			run.Error = err.Error()
		}
	} else {
		// Success
		exitCode := 0
		run.ExitCode = &exitCode
		run.Status = RunStatusSucceeded
	}

	// Save final state
	r.saveRun(run)
}

func (r *LocalRunner) finishRunWithError(run *Run, err error) {
	now := time.Now()
	run.FinishedAt = &now
	run.Status = RunStatusFailed
	run.Error = err.Error()
	r.saveRun(run)
}

func (r *LocalRunner) Wait(ctx context.Context, runID string) (*Run, error) {
	// Check if run exists
	run, err := r.GetRun(ctx, runID)
	if err != nil {
		return nil, err
	}

	// If already finished, return immediately
	if run.Status == RunStatusSucceeded || run.Status == RunStatusFailed || run.Status == RunStatusCancelled {
		return run, nil
	}

	// Poll for completion
	ticker := time.NewTicker(100 * time.Millisecond)
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

func (r *LocalRunner) GetRun(ctx context.Context, runID string) (*Run, error) {
	runPath := filepath.Join(r.runsDir, runID, "run.json")
	data, err := os.ReadFile(runPath)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, fmt.Errorf("run %s not found", runID)
		}
		return nil, fmt.Errorf("failed to read run state: %w", err)
	}

	var run Run
	if err := json.Unmarshal(data, &run); err != nil {
		return nil, fmt.Errorf("failed to parse run state: %w", err)
	}

	return &run, nil
}

func (r *LocalRunner) Cancel(ctx context.Context, runID string) error {
	r.mu.RLock()
	proc, exists := r.runs[runID]
	r.mu.RUnlock()

	if !exists {
		// Check if run exists but is not running
		run, err := r.GetRun(ctx, runID)
		if err != nil {
			return err
		}
		if run.Status == RunStatusSucceeded || run.Status == RunStatusFailed || run.Status == RunStatusCancelled {
			return fmt.Errorf("run %s is already finished with status %s", runID, run.Status)
		}
		return fmt.Errorf("run %s is not currently running", runID)
	}

	// Cancel the context (which will kill the process)
	proc.cancel()

	return nil
}

func (r *LocalRunner) ListRuns(ctx context.Context, status *RunStatus) ([]*Run, error) {
	entries, err := os.ReadDir(r.runsDir)
	if err != nil {
		if os.IsNotExist(err) {
			return []*Run{}, nil
		}
		return nil, fmt.Errorf("failed to read runs directory: %w", err)
	}

	var runs []*Run
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}

		run, err := r.GetRun(ctx, entry.Name())
		if err != nil {
			// Skip runs that can't be read
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

func (r *LocalRunner) saveRun(run *Run) error {
	runPath := filepath.Join(run.RunDir, "run.json")
	data, err := json.MarshalIndent(run, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to marshal run state: %w", err)
	}

	if err := os.WriteFile(runPath, data, 0o644); err != nil {
		return fmt.Errorf("failed to write run state: %w", err)
	}

	return nil
}

// StreamLogs streams the logs of a run to the provided writer
func (r *LocalRunner) StreamLogs(ctx context.Context, runID string, w io.Writer) error {
	run, err := r.GetRun(ctx, runID)
	if err != nil {
		return err
	}

	logFile, err := os.Open(run.LogsPath)
	if err != nil {
		return fmt.Errorf("failed to open log file: %w", err)
	}
	defer logFile.Close()

	_, err = io.Copy(w, logFile)
	return err
}
