package qrunner

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/docker/docker/api/types/container"
	"github.com/docker/docker/api/types/mount"
	"github.com/docker/docker/client"
	"github.com/docker/docker/pkg/stdcopy"
	"github.com/google/uuid"
)

// DockerRunner executes jobs by spinning up Docker containers that internally
// run "qwex run --local <command>". This allows running jobs in isolated
// container environments while delegating the actual command execution to LocalRunner.
//
// Flow:
//  1. Creates .qwex/runs/<runID>/ on host
//  2. Spins up container with volume mount: host_dir → /qwex/runs/<runID>
//  3. Container runs: qwex run --local <original_command>
//  4. LocalRunner inside container writes to /qwex/runs/<runID>/run.json
//  5. Host reads from same directory (it's mounted!)
type DockerRunner struct {
	baseDir string // base directory for .qwex/runs (on host)
	config  ContainerConfig
	client  *client.Client
}

// NewDockerRunner creates a new Docker runner with the given configuration
func NewDockerRunner(config ContainerConfig) (*DockerRunner, error) {
	cwd, _ := os.Getwd()

	dockerClient, err := client.NewClientWithOpts(client.FromEnv, client.WithAPIVersionNegotiation())
	if err != nil {
		return nil, fmt.Errorf("failed to create docker client: %w", err)
	}

	return &DockerRunner{
		baseDir: cwd,
		config:  config,
		client:  dockerClient,
	}, nil
}

// NewDockerRunnerWithBaseDir creates a Docker runner with a specific base directory
func NewDockerRunnerWithBaseDir(baseDir string, config ContainerConfig) (*DockerRunner, error) {
	dockerClient, err := client.NewClientWithOpts(client.FromEnv, client.WithAPIVersionNegotiation())
	if err != nil {
		return nil, fmt.Errorf("failed to create docker client: %w", err)
	}

	return &DockerRunner{
		baseDir: baseDir,
		config:  config,
		client:  dockerClient,
	}, nil
}

func (r *DockerRunner) getRunsDir() string {
	return filepath.Join(r.baseDir, ".qwex", "runs")
}

func (r *DockerRunner) Submit(ctx context.Context, spec JobSpec) (*Run, error) {
	// Generate run ID (using UUIDv7 for lexicographic sorting)
	runID := spec.ID
	if runID == "" {
		uuidV7, err := uuid.NewV7()
		if err != nil {
			return nil, fmt.Errorf("failed to generate UUID: %w", err)
		}
		runID = uuidV7.String()
	}

	// Create run directory (on host) for tracking
	runsDir := r.getRunsDir()
	runDir := filepath.Join(runsDir, runID)
	if err := os.MkdirAll(runDir, 0o755); err != nil {
		return nil, fmt.Errorf("failed to create run directory: %w", err)
	}

	// Use image from config (in the future, could come from spec.Image)
	image := r.config.Image

	// Run command DIRECTLY (no qwex wrapper!)
	fullCmd := append([]string{spec.Command}, spec.Args...)

	// Container paths (inside container)
	containerRunDir := filepath.Join("/qwex/runs", runID)
	containerWorkDir := "/workspace"

	// Build Docker mounts
	mounts := []mount.Mount{
		{
			Type:     mount.TypeBind,
			Source:   runDir,          // Host path for run tracking
			Target:   containerRunDir, // Container path
			ReadOnly: false,
		},
	}

	// Mount the working directory if specified (where user's code/scripts are)
	if spec.WorkingDir != "" {
		mounts = append(mounts, mount.Mount{
			Type:     mount.TypeBind,
			Source:   spec.WorkingDir,  // Host working directory
			Target:   containerWorkDir, // Container working directory
			ReadOnly: true,             // Read-only for safety
		})
	}

	// Add user-defined mounts
	for _, m := range r.config.Mounts {
		mounts = append(mounts, mount.Mount{
			Type:     mount.Type(m.Type),
			Source:   m.Source,
			Target:   m.Destination,
			ReadOnly: m.ReadOnly,
		})
	}

	// Build environment variables
	env := []string{}
	for k, v := range spec.Env {
		env = append(env, fmt.Sprintf("%s=%s", k, v))
	}
	env = append(env,
		fmt.Sprintf("QWEX_RUN_ID=%s", runID),
		fmt.Sprintf("QWEX_RUN_DIR=%s", containerRunDir),
		"QWEX_BACKEND=docker",
	)

	// Create log file path (we'll write Docker logs here)
	logsPath := filepath.Join(runDir, "stdout.log")

	// Set working directory - use containerWorkDir if we mounted the working dir
	workDir := containerWorkDir
	if spec.WorkingDir == "" {
		workDir = "/" // Default to root if no working dir
	}

	// Create container
	containerConfig := &container.Config{
		Image:      image,
		Cmd:        fullCmd,
		Env:        env,
		WorkingDir: workDir,
	}

	hostConfig := &container.HostConfig{
		Mounts: mounts,
	}

	resp, err := r.client.ContainerCreate(ctx, containerConfig, hostConfig, nil, nil, fmt.Sprintf("qwex-%s", runID[:8]))
	if err != nil {
		return nil, fmt.Errorf("failed to create container: %w", err)
	}

	containerID := resp.ID

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
		Metadata: map[string]string{
			"run_dir":      runDir,
			"logs_path":    logsPath,
			"container_id": containerID,
			"backend":      "docker",
			"image":        image,
		},
		RunDir:   runDir,
		LogsPath: logsPath,
	}

	// Save initial state
	if err := r.saveRun(run); err != nil {
		return nil, fmt.Errorf("failed to save run state: %w", err)
	}

	// Start container
	if err := r.client.ContainerStart(ctx, containerID, container.StartOptions{}); err != nil {
		return nil, fmt.Errorf("failed to start container: %w", err)
	}

	// Update status to running
	now = time.Now()
	run.StartedAt = &now
	run.Status = RunStatusRunning
	if err := r.saveRun(run); err != nil {
		return nil, fmt.Errorf("failed to save run state: %w", err)
	}

	return run, nil
}

// captureLogs retrieves container logs and writes them to the log file
func (r *DockerRunner) captureLogs(ctx context.Context, containerID string, run *Run) {
	logFile, err := os.Create(run.LogsPath)
	if err != nil {
		return // Can't write logs, but don't fail the run
	}
	defer logFile.Close()

	options := container.LogsOptions{
		ShowStdout: true,
		ShowStderr: true,
		Follow:     false,
		Timestamps: false,
	}

	logReader, err := r.client.ContainerLogs(ctx, containerID, options)
	if err != nil {
		return
	}
	defer logReader.Close()

	// Docker log stream is multiplexed with 8-byte headers
	// Use stdcopy to properly demultiplex stdout/stderr
	_, err = stdcopy.StdCopy(logFile, logFile, logReader)
	if err != nil {
		// Log error but don't fail the run
		return
	}
}

func (r *DockerRunner) Wait(ctx context.Context, runID string) (*Run, error) {
	run, err := r.GetRun(ctx, runID)
	if err != nil {
		return nil, err
	}

	if run.Status == RunStatusSucceeded || run.Status == RunStatusFailed || run.Status == RunStatusCancelled {
		return run, nil
	}

	containerID := run.Metadata["container_id"]
	if containerID == "" {
		return nil, fmt.Errorf("container ID not found in run metadata")
	}

	// Wait for container to finish
	statusCh, errCh := r.client.ContainerWait(ctx, containerID, container.WaitConditionNotRunning)

	var exitCode int64
	select {
	case err := <-errCh:
		if err != nil {
			return nil, fmt.Errorf("error waiting for container: %w", err)
		}
	case status := <-statusCh:
		exitCode = status.StatusCode
	case <-ctx.Done():
		return nil, ctx.Err()
	}

	// Update the run with final status (don't rely on trackContainer goroutine)
	finishTime := time.Now()
	run.FinishedAt = &finishTime
	exitCodeInt := int(exitCode)
	run.ExitCode = &exitCodeInt

	if exitCode == 0 {
		run.Status = RunStatusSucceeded
	} else {
		run.Status = RunStatusFailed
		run.Error = fmt.Sprintf("container exited with code %d", exitCode)
	}

	// Capture logs
	r.captureLogs(ctx, containerID, run)

	// Save final state
	r.saveRun(run)

	// Clean up container (remove it after completion since it's ephemeral)
	removeErr := r.client.ContainerRemove(ctx, containerID, container.RemoveOptions{
		Force: true, // Force remove even if still running
	})
	if removeErr != nil {
		// Log error but don't fail - run completed successfully
		// Container will be cleaned up later manually if needed
	}

	return run, nil
}

func (r *DockerRunner) GetRun(ctx context.Context, runID string) (*Run, error) {
	// Read run state from the mounted directory
	// LocalRunner inside the container writes to run.json
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

func (r *DockerRunner) Cancel(ctx context.Context, runID string) error {
	run, err := r.GetRun(ctx, runID)
	if err != nil {
		return err
	}

	containerID := run.Metadata["container_id"]
	if containerID == "" {
		return fmt.Errorf("container ID not found in run metadata")
	}

	// Stop the container (10 second timeout, then kill)
	timeout := 10
	if err := r.client.ContainerStop(ctx, containerID, container.StopOptions{Timeout: &timeout}); err != nil {
		// If container is already stopped, that's fine
		if !strings.Contains(err.Error(), "is not running") {
			return fmt.Errorf("failed to stop container: %w", err)
		}
	}

	return nil
}

func (r *DockerRunner) ListRuns(ctx context.Context, status *RunStatus) ([]*Run, error) {
	// Read from the runs directory (same as LocalRunner)
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

func (r *DockerRunner) saveRun(run *Run) error {
	runPath := filepath.Join(run.Metadata["run_dir"], "run.json")
	data, err := json.MarshalIndent(run, "", "  ")
	if err != nil {
		return fmt.Errorf("failed to marshal run state: %w", err)
	}

	if err := os.WriteFile(runPath, data, 0o644); err != nil {
		return fmt.Errorf("failed to write run state: %w", err)
	}

	return nil
}

// StreamLogs streams the logs from the Docker container
func (r *DockerRunner) StreamLogs(ctx context.Context, runID string, w io.Writer) error {
	run, err := r.GetRun(ctx, runID)
	if err != nil {
		return err
	}

	containerID := run.Metadata["container_id"]
	if containerID == "" {
		return fmt.Errorf("container ID not found in run metadata")
	}

	// Get container logs
	options := container.LogsOptions{
		ShowStdout: true,
		ShowStderr: true,
		Follow:     false,
		Timestamps: false,
	}

	logReader, err := r.client.ContainerLogs(ctx, containerID, options)
	if err != nil {
		return fmt.Errorf("failed to get container logs: %w", err)
	}
	defer logReader.Close()

	_, err = io.Copy(w, logReader)
	return err
}

// Close closes the Docker client connection
func (r *DockerRunner) Close() error {
	if r.client != nil {
		return r.client.Close()
	}
	return nil
}
