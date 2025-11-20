package cmd

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/quatton/qwex/pkg/qrunner"
	"github.com/spf13/cobra"
)

var (
	runLocal   bool
	runBackend string
	runName    string
)

var runCmd = &cobra.Command{
	Use:   "run [flags] -- <command> [args...]",
	Short: "Run a command and track its execution",
	Long: `Run a command locally or on qwex cloud and track its execution.

Examples:
  # Run a simple command locally
  qwex run --local -- echo "Hello World"
  
  # Run a Python script with arguments
  qwex run --local -- python train.py --epochs 100
  
  # Run with a custom name
  qwex run --local --name "training-run" -- python train.py`,
	Args: cobra.MinimumNArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg, err := GetConfig(cmd)
		if err != nil {
			return err
		}

		// Parse command and args
		command := args[0]
		cmdArgs := args[1:]

		// Create job spec
		spec := qrunner.JobSpec{
			Name:    runName,
			Command: command,
			Args:    cmdArgs,
			Env:     cfg.Env,
		}

		// Determine working directory
		// If config file was used, base working dir relative to config file location
		configFileUsed := cfg.ConfigFileUsed()
		var baseDir string
		if configFileUsed != "" {
			// Get directory containing the config file
			absConfigPath, err := filepath.Abs(configFileUsed)
			if err != nil {
				return fmt.Errorf("resolving config path: %w", err)
			}
			baseDir = filepath.Dir(absConfigPath)
		} else {
			// No config file, use current directory
			var err error
			baseDir, err = os.Getwd()
			if err != nil {
				return fmt.Errorf("getting working directory: %w", err)
			}
		}

		// Apply working_dir from config (relative to baseDir) or use baseDir
		if cfg.WorkingDir != "" {
			if filepath.IsAbs(cfg.WorkingDir) {
				spec.WorkingDir = cfg.WorkingDir
			} else {
				spec.WorkingDir = filepath.Join(baseDir, cfg.WorkingDir)
			}
		} else {
			spec.WorkingDir = baseDir
		}

		// Default name if not provided
		if spec.Name == "" {
			spec.Name = command
		}

		ctx := context.Background()

		// Determine backend: CLI flag > config file > default to local
		backend := "local"
		if runBackend != "" {
			backend = runBackend
		} else if cfg.Backend != "" {
			backend = cfg.Backend
		} else if runLocal {
			backend = "local"
		}

		// Create appropriate runner based on backend
		var runner qrunner.Runner

		switch backend {
		case "local":
			// Create local runner with base directory set to the spec's working directory
			runner = qrunner.NewLocalRunnerWithBaseDir(spec.WorkingDir)

		case "docker":
			// Create Docker runner with image from config
			config := qrunner.DefaultContainerConfig()
			if cfg.Image != "" {
				config.Image = cfg.Image
			}
			// Set base directory to spec.WorkingDir so .qwex is created relative to qwex.yaml
			dockerRunner, dockerErr := qrunner.NewDockerRunnerWithBaseDir(spec.WorkingDir, config)
			if dockerErr != nil {
				return fmt.Errorf("creating docker runner: %w", dockerErr)
			}
			defer dockerRunner.Close()
			runner = dockerRunner

		default:
			return fmt.Errorf("unsupported backend: %s (supported: local, docker)", backend)
		}

		// Submit the run
		fmt.Printf("Submitting run: %s\n", spec.Name)
		fmt.Printf("Backend: %s\n", backend)
		if backend == "docker" && cfg.Image != "" {
			fmt.Printf("Image: %s\n", cfg.Image)
		}
		fmt.Printf("Command: %s %v\n", spec.Command, spec.Args)
		fmt.Printf("Working directory: %s\n", spec.WorkingDir)

		run, err := runner.Submit(ctx, spec)
		if err != nil {
			return fmt.Errorf("submitting run: %w", err)
		}

		fmt.Printf("\n✓ Run submitted successfully!\n")
		fmt.Printf("Run ID: %s\n", run.ID)
		fmt.Printf("Status: %s\n", run.Status)
		fmt.Printf("Run directory: %s\n", run.RunDir)
		fmt.Printf("Logs: %s\n", run.LogsPath)

		// Wait for completion
		fmt.Println("\nWaiting for run to complete...")
		finalRun, err := runner.Wait(ctx, run.ID)
		if err != nil {
			return fmt.Errorf("waiting for run: %w", err)
		}

		// Print results
		fmt.Printf("\n")
		fmt.Printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
		fmt.Printf("Run completed: %s\n", finalRun.Status)
		fmt.Printf("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

		if finalRun.ExitCode != nil {
			fmt.Printf("Exit code: %d\n", *finalRun.ExitCode)
		}

		if finalRun.StartedAt != nil && finalRun.FinishedAt != nil {
			duration := finalRun.FinishedAt.Sub(*finalRun.StartedAt)
			fmt.Printf("Duration: %s\n", duration.Round(time.Millisecond))
		}

		// Read and display logs
		fmt.Printf("\nLogs:\n")
		fmt.Printf("─────────────────────────────────────────\n")

		logsContent, err := os.ReadFile(finalRun.LogsPath)
		if err != nil {
			fmt.Printf("(Could not read logs: %v)\n", err)
		} else {
			fmt.Print(string(logsContent))
		}

		fmt.Printf("─────────────────────────────────────────\n")

		// Show relative path for convenience
		relPath, err := filepath.Rel(".", finalRun.RunDir)
		if err == nil {
			fmt.Printf("\nFull logs available at: %s\n", relPath)
		} else {
			fmt.Printf("\nFull logs available at: %s\n", finalRun.RunDir)
		}

		// Exit with same code as the run
		if finalRun.ExitCode != nil && *finalRun.ExitCode != 0 {
			os.Exit(*finalRun.ExitCode)
		}

		return nil
	},
}

func init() {
	rootCmd.AddCommand(runCmd)
	runCmd.Flags().BoolVar(&runLocal, "local", false, "Run locally (deprecated: use --backend=local)")
	runCmd.Flags().StringVar(&runBackend, "backend", "", "Backend to use: local, docker (default: from config or local)")
	runCmd.Flags().StringVar(&runName, "name", "", "Custom name for the run")
}
