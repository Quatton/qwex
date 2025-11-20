package qrunner

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestLocalRunner_Submit(t *testing.T) {
	// Create temp directory for test
	tempDir := t.TempDir()
	oldWd, _ := os.Getwd()
	os.Chdir(tempDir)
	defer os.Chdir(oldWd)

	runner := NewLocalRunner()
	ctx := context.Background()

	spec := JobSpec{
		Name:    "test-job",
		Command: "echo",
		Args:    []string{"hello", "world"},
	}

	run, err := runner.Submit(ctx, spec)
	if err != nil {
		t.Fatalf("Submit failed: %v", err)
	}

	if run.ID == "" {
		t.Error("Run ID should not be empty")
	}

	if run.Status != RunStatusPending {
		t.Errorf("Expected status PENDING, got %s", run.Status)
	}

	// Wait for completion
	finalRun, err := runner.Wait(ctx, run.ID)
	if err != nil {
		t.Fatalf("Wait failed: %v", err)
	}

	if finalRun.Status != RunStatusSucceeded {
		t.Errorf("Expected status SUCCEEDED, got %s (error: %s)", finalRun.Status, finalRun.Error)
	}

	if finalRun.ExitCode == nil || *finalRun.ExitCode != 0 {
		t.Errorf("Expected exit code 0, got %v", finalRun.ExitCode)
	}

	// Verify log file exists
	if _, err := os.Stat(finalRun.LogsPath); os.IsNotExist(err) {
		t.Error("Log file should exist")
	}

	// Verify run.json exists
	runJSONPath := filepath.Join(finalRun.RunDir, "run.json")
	if _, err := os.Stat(runJSONPath); os.IsNotExist(err) {
		t.Error("run.json should exist")
	}
}

func TestLocalRunner_FailedCommand(t *testing.T) {
	tempDir := t.TempDir()
	oldWd, _ := os.Getwd()
	os.Chdir(tempDir)
	defer os.Chdir(oldWd)

	runner := NewLocalRunner()
	ctx := context.Background()

	spec := JobSpec{
		Name:    "failing-job",
		Command: "sh",
		Args:    []string{"-c", "exit 1"},
	}

	run, err := runner.Submit(ctx, spec)
	if err != nil {
		t.Fatalf("Submit failed: %v", err)
	}

	// Wait for completion
	finalRun, err := runner.Wait(ctx, run.ID)
	if err != nil {
		t.Fatalf("Wait failed: %v", err)
	}

	if finalRun.Status != RunStatusFailed {
		t.Errorf("Expected status FAILED, got %s", finalRun.Status)
	}

	if finalRun.ExitCode == nil || *finalRun.ExitCode != 1 {
		t.Errorf("Expected exit code 1, got %v", finalRun.ExitCode)
	}
}

func TestLocalRunner_Cancel(t *testing.T) {
	tempDir := t.TempDir()
	oldWd, _ := os.Getwd()
	os.Chdir(tempDir)
	defer os.Chdir(oldWd)

	runner := NewLocalRunner()
	ctx := context.Background()

	// Long-running command
	spec := JobSpec{
		Name:    "long-job",
		Command: "sleep",
		Args:    []string{"10"},
	}

	run, err := runner.Submit(ctx, spec)
	if err != nil {
		t.Fatalf("Submit failed: %v", err)
	}

	// Give it a moment to start
	time.Sleep(100 * time.Millisecond)

	// Cancel the run
	if err := runner.Cancel(ctx, run.ID); err != nil {
		t.Fatalf("Cancel failed: %v", err)
	}

	// Wait for it to finish
	finalRun, err := runner.Wait(ctx, run.ID)
	if err != nil {
		t.Fatalf("Wait failed: %v", err)
	}

	if finalRun.Status != RunStatusCancelled {
		t.Errorf("Expected status CANCELLED, got %s", finalRun.Status)
	}
}

func TestLocalRunner_ListRuns(t *testing.T) {
	tempDir := t.TempDir()
	oldWd, _ := os.Getwd()
	os.Chdir(tempDir)
	defer os.Chdir(oldWd)

	runner := NewLocalRunner()
	ctx := context.Background()

	// Submit multiple runs
	for i := 0; i < 3; i++ {
		spec := JobSpec{
			Name:    "test-job",
			Command: "echo",
			Args:    []string{"test"},
		}
		_, err := runner.Submit(ctx, spec)
		if err != nil {
			t.Fatalf("Submit failed: %v", err)
		}
	}

	// Wait a bit for execution
	time.Sleep(200 * time.Millisecond)

	// List all runs
	runs, err := runner.ListRuns(ctx, nil)
	if err != nil {
		t.Fatalf("ListRuns failed: %v", err)
	}

	if len(runs) != 3 {
		t.Errorf("Expected 3 runs, got %d", len(runs))
	}

	// Filter by succeeded status
	succeededStatus := RunStatusSucceeded
	succeededRuns, err := runner.ListRuns(ctx, &succeededStatus)
	if err != nil {
		t.Fatalf("ListRuns with filter failed: %v", err)
	}

	if len(succeededRuns) != 3 {
		t.Errorf("Expected 3 succeeded runs, got %d", len(succeededRuns))
	}
}
