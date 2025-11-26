package qrunner

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
	"github.com/quatton/qwex/pkg/qart"
)

type LocalRunner struct {
	baseDir   string     // base directory for .qwex/runs
	artifacts qart.Store // artifact storage (optional)
	mu        sync.RWMutex
	runs      map[string]*runProcess // in-memory tracking of active runs
}

// runProcess tracks an active process
type runProcess struct {
	cmd    *exec.Cmd
	run    *Run
	cancel context.CancelFunc
}

// LocalRunnerOption configures a LocalRunner
type LocalRunnerOption func(*LocalRunner)

// WithArtifactStore sets the artifact storage for the runner
func WithArtifactStore(store qart.Store) LocalRunnerOption {
	return func(r *LocalRunner) {
		r.artifacts = store
	}
}

// WithBaseDir sets the base directory for runs
func WithBaseDir(baseDir string) LocalRunnerOption {
	return func(r *LocalRunner) {
		r.baseDir = baseDir
	}
}

func NewLocalRunner(opts ...LocalRunnerOption) *LocalRunner {
	cwd, _ := os.Getwd()
	r := &LocalRunner{
		baseDir: cwd,
		runs:    make(map[string]*runProcess),
	}
	for _, opt := range opts {
		opt(r)
	}
	return r
}

// getRunsDir returns the runs directory
func (r *LocalRunner) getRunsDir() string {
	return filepath.Join(r.baseDir, ".qwex", "runs")
}

func (r *LocalRunner) Submit(ctx context.Context, spec JobSpec) (*Run, error) {
	// Generate run ID (using UUIDv7 for lexicographic sorting)
	runID := spec.ID
	if runID == "" {
		uuidV7, err := uuid.NewV7()
		if err != nil {
			return nil, fmt.Errorf("failed to generate UUID: %w", err)
		}
		runID = uuidV7.String()
	}

	// Create run directory (.qwex/runs/<runID> in the base directory)
	runsDir := r.getRunsDir()
	runDir := filepath.Join(runsDir, runID)
	if err := os.MkdirAll(runDir, 0o755); err != nil {
		return nil, fmt.Errorf("failed to create run directory: %w", err)
	}

	// Create logs paths
	logsPath := filepath.Join(runDir, "stdout.log")
	stderrPath := filepath.Join(runDir, "stderr.log")

	// Initialize run object
	now := time.Now()
	run := &Run{
		ID:         runID,
		Name:       spec.Name,
		Status:     RunStatusPending,
		Command:    spec.Command,
		Args:       spec.Args,
		Env:        spec.Env,
		CreatedAt:  now,
		Metadata:   make(map[string]string),
		RunDir:     runDir,
		LogsPath:   logsPath,
		StderrPath: stderrPath,
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

	// Create stderr file
	stderrFile, err := os.Create(run.StderrPath)
	if err != nil {
		r.finishRunWithError(run, fmt.Errorf("failed to create stderr file: %w", err))
		return
	}
	defer stderrFile.Close()

	// Redirect stdout and stderr to separate files
	cmd.Stdout = logFile
	cmd.Stderr = stderrFile

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
		} else if exitErr, ok := err.(*exec.ExitError); ok {
			// Process exited with non-zero code
			exitCode := exitErr.ExitCode()
			run.ExitCode = &exitCode
			run.Status = RunStatusFailed
		} else {
			// Other error (failed to start, etc.) - write to stderr.log
			run.Status = RunStatusFailed
			os.WriteFile(run.StderrPath, []byte(err.Error()), 0o644)
		}
	} else {
		// Success
		exitCode := 0
		run.ExitCode = &exitCode
		run.Status = RunStatusSucceeded
	}

	// Upload artifacts if storage is configured
	r.uploadArtifacts(ctx, run)

	// Save final state
	r.saveRun(run)
}

func (r *LocalRunner) finishRunWithError(run *Run, err error) {
	now := time.Now()
	run.FinishedAt = &now
	run.Status = RunStatusFailed
	// Write error to stderr.log
	os.WriteFile(run.StderrPath, []byte(err.Error()), 0o644)
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
	runPath := filepath.Join(r.getRunsDir(), runID, "run.json")
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
	entries, err := os.ReadDir(r.getRunsDir())
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

// uploadArtifacts uploads run artifacts to storage if configured
func (r *LocalRunner) uploadArtifacts(ctx context.Context, run *Run) {
	if r.artifacts == nil {
		return
	}

	// Upload stdout.log
	if run.LogsPath != "" {
		logFile, err := os.Open(run.LogsPath)
		if err == nil {
			defer logFile.Close()
			stat, _ := logFile.Stat()
			key := qart.RunArtifactKey(run.ID, "stdout.log")
			artifact, err := r.artifacts.Upload(ctx, key, logFile, "text/plain", map[string]string{
				"run_id": run.ID,
			})
			if err == nil {
				run.Artifacts = append(run.Artifacts, RunArtifact{
					Key:         artifact.Key,
					Filename:    "stdout.log",
					Size:        stat.Size(),
					ContentType: "text/plain",
				})
			}
		}
	}

	// Upload stderr.log
	if run.StderrPath != "" {
		stderrFile, err := os.Open(run.StderrPath)
		if err == nil {
			defer stderrFile.Close()
			stat, _ := stderrFile.Stat()
			key := qart.RunArtifactKey(run.ID, "stderr.log")
			artifact, err := r.artifacts.Upload(ctx, key, stderrFile, "text/plain", map[string]string{
				"run_id": run.ID,
			})
			if err == nil {
				run.Artifacts = append(run.Artifacts, RunArtifact{
					Key:         artifact.Key,
					Filename:    "stderr.log",
					Size:        stat.Size(),
					ContentType: "text/plain",
				})
			}
		}
	}

	// Upload run.json metadata
	runJSONPath := filepath.Join(run.RunDir, "run.json")
	if runJSON, err := os.Open(runJSONPath); err == nil {
		defer runJSON.Close()
		stat, _ := runJSON.Stat()
		key := qart.RunArtifactKey(run.ID, "run.json")
		artifact, err := r.artifacts.Upload(ctx, key, runJSON, "application/json", map[string]string{
			"run_id": run.ID,
		})
		if err == nil {
			run.Artifacts = append(run.Artifacts, RunArtifact{
				Key:         artifact.Key,
				Filename:    "run.json",
				Size:        stat.Size(),
				ContentType: "application/json",
			})
		}
	}
}

// GetLogs returns the logs for a run
func (r *LocalRunner) GetLogs(ctx context.Context, runID string) (io.ReadCloser, error) {
	run, err := r.GetRun(ctx, runID)
	if err != nil {
		return nil, err
	}

	logFile, err := os.Open(run.LogsPath)
	if err != nil {
		return nil, fmt.Errorf("failed to open log file: %w", err)
	}

	return logFile, nil
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
