package qrunner

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/google/uuid"
)

// DockerRunner executes jobs by spinning up Docker containers that internally
// run "qwex run --local <command>". This allows running jobs in isolated
// container environments while delegating the actual command execution to LocalRunner.
type DockerRunner struct {
	baseDir string // base directory for .qwex/runs (on host)
	config  ContainerConfig
	// TODO: add docker client when implementing
	// client *docker.Client
}

// NewDockerRunner creates a new Docker runner with the given configuration
func NewDockerRunner(config ContainerConfig) *DockerRunner {
	cwd, _ := os.Getwd()
	return &DockerRunner{
		baseDir: cwd,
		config:  config,
	}
}

// NewDockerRunnerWithBaseDir creates a Docker runner with a specific base directory
func NewDockerRunnerWithBaseDir(baseDir string, config ContainerConfig) *DockerRunner {
	return &DockerRunner{
		baseDir: baseDir,
		config:  config,
	}
}

func (r *DockerRunner) getRunsDir() string {
	return filepath.Join(r.baseDir, ".qwex", "runs")
}

func (r *DockerRunner) Submit(ctx context.Context, spec JobSpec) (*Run, error) {
	// Generate run ID
	runID := uuid.New().String()
	if spec.ID != "" {
		runID = spec.ID
	}

	// Create run directory (on host, will be mounted into container)
	runsDir := r.getRunsDir()
	runDir := filepath.Join(runsDir, runID)
	if err := os.MkdirAll(runDir, 0o755); err != nil {
		return nil, fmt.Errorf("failed to create run directory: %w", err)
	}

	// Wrap the command to run via "qwex run --local"
	// Original: echo hello world
	// Wrapped:  qwex run --local echo hello world
	wrappedCmd, wrappedArgs := WrapCommandForLocal(spec.Command, spec.Args)

	// Create container config
	containerConfig := r.buildContainerConfig(spec, runDir, wrappedCmd, wrappedArgs)

	// Initialize run object
	now := time.Now()
	run := &Run{
		ID:        runID,
		JobID:     spec.Name,
		Status:    RunStatusPending,
		Command:   spec.Command, // Store original command
		Args:      spec.Args,
		Env:       spec.Env,
		CreatedAt: now,
		Metadata: map[string]string{
			"run_dir":         runDir,
			"logs_path":       filepath.Join(runDir, "stdout.log"),
			"wrapped_command": wrappedCmd, // Store wrapped command for debugging
			"backend":         "docker",
			// TODO: add docker container ID when implementing
			// "container_id": containerID,
		},
		RunDir:   runDir,
		LogsPath: filepath.Join(runDir, "stdout.log"),
	}

	// Save initial state
	if err := r.saveRun(run); err != nil {
		return nil, fmt.Errorf("failed to save run state: %w", err)
	}

	// TODO: Implement Docker container creation and start
	// This would call Docker API to:
	// 1. Create container with containerConfig
	// 2. Start the container
	// 3. Store container ID in run.Metadata
	fmt.Printf("TODO: Create Docker container with config: %+v\n", containerConfig)

	return run, nil
}

// buildContainerConfig constructs the Docker container configuration
// This is where we translate our shared ContainerConfig into Docker-specific config
func (r *DockerRunner) buildContainerConfig(spec JobSpec, runDir, command string, args []string) map[string]interface{} {
	// Mount the run directory into the container
	// Host: /home/user/.qwex/runs/abc-123
	// Container: /qwex/runs/abc-123
	containerRunDir := filepath.Join("/qwex/runs", filepath.Base(runDir))

	mounts := []Mount{
		{
			Type:        "bind",
			Source:      runDir,
			Destination: containerRunDir,
			ReadOnly:    false,
		},
	}

	// Add user-defined mounts
	mounts = append(mounts, r.config.Mounts...)

	// Build environment variables
	// Include spec.Env and add qwex-specific vars
	env := make(map[string]string)
	for k, v := range spec.Env {
		env[k] = v
	}
	env["QWEX_RUN_DIR"] = containerRunDir // Inside container path
	env["QWEX_BACKEND"] = "docker"

	// This is a pseudo-config showing what would be passed to Docker API
	return map[string]interface{}{
		"image":   r.config.Image,
		"command": command,
		"args":    args,
		"env":     env,
		"mounts":  mounts,
		"resources": map[string]interface{}{
			"cpu_request":    r.config.Resources.CPURequest,
			"memory_request": r.config.Resources.MemoryRequest,
			"cpu_limit":      r.config.Resources.CPULimit,
			"memory_limit":   r.config.Resources.MemoryLimit,
		},
		"network_mode": r.config.NetworkMode,
		"working_dir":  containerRunDir,
	}
}

func (r *DockerRunner) Wait(ctx context.Context, runID string) (*Run, error) {
	// Similar to LocalRunner: poll for completion
	run, err := r.GetRun(ctx, runID)
	if err != nil {
		return nil, err
	}

	if run.Status == RunStatusSucceeded || run.Status == RunStatusFailed || run.Status == RunStatusCancelled {
		return run, nil
	}

	// TODO: Use Docker API to wait for container
	// For now, poll the run.json file (LocalRunner inside container updates it)
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
	// TODO: Call Docker API to stop/kill container
	run, err := r.GetRun(ctx, runID)
	if err != nil {
		return err
	}

	containerID := run.Metadata["container_id"]
	if containerID == "" {
		return fmt.Errorf("container ID not found in run metadata")
	}

	// TODO: Implement
	// r.client.ContainerStop(ctx, containerID, timeout)
	fmt.Printf("TODO: Stop Docker container %s\n", containerID)

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
