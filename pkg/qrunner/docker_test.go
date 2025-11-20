package qrunner

import (
	"context"
	"testing"
	"time"
)

// TestDockerRunnerBasic tests basic DockerRunner functionality
// This assumes:
// 1. Docker daemon is running
// 2. qwex:latest image exists with qwex binary installed
func TestDockerRunnerBasic(t *testing.T) {
	t.Skip("Requires Docker daemon and qwex:latest image - run manually")

	config := DefaultContainerConfig()
	runner, err := NewDockerRunner(config)
	if err != nil {
		t.Fatalf("Failed to create DockerRunner: %v", err)
	}
	defer runner.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	// Submit a simple echo job
	spec := JobSpec{
		Name:    "test-echo",
		Command: "echo",
		Args:    []string{"Hello from Docker!"},
	}

	run, err := runner.Submit(ctx, spec)
	if err != nil {
		t.Fatalf("Failed to submit job: %v", err)
	}

	t.Logf("Submitted run %s with container %s", run.ID, run.Metadata["container_id"])

	// Wait for completion
	finalRun, err := runner.Wait(ctx, run.ID)
	if err != nil {
		t.Fatalf("Failed to wait for run: %v", err)
	}

	t.Logf("Run finished with status: %s", finalRun.Status)

	if finalRun.Status != RunStatusSucceeded {
		t.Errorf("Expected status succeeded, got %s", finalRun.Status)
	}

	if finalRun.ExitCode == nil || *finalRun.ExitCode != 0 {
		t.Errorf("Expected exit code 0, got %v", finalRun.ExitCode)
	}
}
