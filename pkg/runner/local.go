package runner

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"time"
)

type LocalRunner struct {
	runsDir string
	outDir  string
}

func NewLocalRunner() *LocalRunner {
	// Use .qwex in current directory (project root) or home?
	// User said: "if it's local, it just runs here and put all the files inside .qwex/runs and .qwex/out"
	// This implies relative to CWD (project root).
	cwd, _ := os.Getwd()
	return &LocalRunner{
		runsDir: filepath.Join(cwd, ".qwex", "runs"),
		outDir:  filepath.Join(cwd, ".qwex", "out"),
	}
}

func (r *LocalRunner) Run(ctx context.Context, spec RunSpec) error {
	// 1. Prepare Directories
	runDir := filepath.Join(r.runsDir, spec.ID)
	if err := os.MkdirAll(runDir, 0755); err != nil {
		return fmt.Errorf("failed to create run dir: %w", err)
	}
	if err := os.MkdirAll(r.outDir, 0755); err != nil {
		return fmt.Errorf("failed to create out dir: %w", err)
	}

	// 2. Setup Logging
	logPath := filepath.Join(r.outDir, fmt.Sprintf("%s.log", spec.ID))
	logFile, err := os.Create(logPath)
	if err != nil {
		return fmt.Errorf("failed to create log file: %w", err)
	}
	defer logFile.Close()
	
	writer := logFile // io.MultiWriter(os.Stdout, logFile)
	fmt.Fprintf(writer, "Job ID: %s\nCommand: %s\nCommit: %s\n\n", spec.ID, spec.Command, spec.CommitHash)
	fmt.Printf("📝 Logs: %s\n", logPath)

	// 3. Clone/Checkout
	// Since we are local, we can try to use `git clone` directly.
	// Or `git worktree` if we are in the repo?
	// User said: "checking out to commit id, run it"
	// Cloning is safer for isolation.
	// We assume the user has credentials for the repo in their environment (ssh-agent, credential helper).
	
	fmt.Fprintf(writer, "--- Cloning ---\n")
	cloneCmd := exec.CommandContext(ctx, "git", "clone", spec.RepoURL, runDir)
	cloneCmd.Stdout = writer
	cloneCmd.Stderr = writer
	if err := cloneCmd.Run(); err != nil {
		return fmt.Errorf("clone failed: %w", err)
	}

	fmt.Fprintf(writer, "\n--- Checking out %s ---\n", spec.CommitHash)
	checkoutCmd := exec.CommandContext(ctx, "git", "-C", runDir, "checkout", spec.CommitHash)
	checkoutCmd.Stdout = writer
	checkoutCmd.Stderr = writer
	if err := checkoutCmd.Run(); err != nil {
		return fmt.Errorf("checkout failed: %w", err)
	}

	// 4. Execute
	fmt.Fprintf(writer, "\n--- Executing ---\n")
	runCmd := exec.CommandContext(ctx, "/bin/sh", "-c", spec.Command)
	runCmd.Dir = runDir
	runCmd.Stdout = writer
	runCmd.Stderr = writer
	runCmd.Env = os.Environ()
	for k, v := range spec.Env {
		runCmd.Env = append(runCmd.Env, fmt.Sprintf("%s=%s", k, v))
	}

	start := time.Now()
	err = runCmd.Run()
	duration := time.Since(start)
	
	fmt.Fprintf(writer, "\n--- Finished in %s ---\n", duration)
	
	if err != nil {
		fmt.Printf("❌ Job failed. Check logs.\n")
		return err
	}
	
	fmt.Printf("✅ Job completed in %s\n", duration)
	return nil
}
