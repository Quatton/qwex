package cmd

import (
	"context"
	"fmt"
	"os"
	"time"

	"github.com/Quatton/qwex/apps/qwexctl/internal/batch"
	"github.com/Quatton/qwex/apps/qwexctl/internal/connect"
	"github.com/Quatton/qwex/apps/qwexctl/internal/pods"
	"github.com/spf13/cobra"
)

var (
	follow    bool
	batchName string
	image     string
)

var batchCmd = &cobra.Command{
	Use:   "batch [command] [args...]",
	Short: "Submit a batch job to the remote workspace",
	Long: `Submit a batch job that runs in an isolated worktree.
The job will sync your current commit and execute the specified command.`,
	Args: cobra.MinimumNArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		localRepoPath := connect.GetLocalRepoPath(cfgFile)

		ctx := cmd.Context()
		svc := ctx.Value("service").(*Service)

		podService := &pods.Service{K8s: svc.K8s.Clientset, Namespace: svc.Namespace}
		dep, err := podService.GetOrCreateDevelopmentDeployment(ctx, pods.Active)
		if err != nil {
			return err
		}

		pod, err := podService.GetPodFromDeployment(ctx, dep)
		if err != nil {
			return err
		}

		connectService := connect.NewService(svc.K8s.Clientset, svc.K8s.Config, namespace, pod.Name, pods.SyncContainerName, localRepoPath)

		// Make this configurable later?
		targetWorkDir := batch.BatchWorkDir

		targetImage := image
		if targetImage == "" {
			targetImage = batch.DemoImage
		}

		if args[0] == "--" {
			args = args[1:]
		}

		command := []string{args[0]}
		var cmdArgs []string
		if len(args) > 1 {
			cmdArgs = args[1:]
		}

		batchService := batch.NewService(connectService, "", targetImage, command, cmdArgs, targetWorkDir, batchName)

		fmt.Println("🔄 Syncing workspace...")
		job, err := batchService.EnsureSyncAndSubmitJob(ctx)
		if err != nil {
			return err
		}

		runID := job.Labels["qwex.dev/run-id"]
		fmt.Printf("✅ Job submitted: %s (run-id: %s)\n", job.Name, runID)

		if follow {
			ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
			defer cancel()

			if err := batchService.FollowRunLogs(ctx, runID, os.Stdout); err != nil {
				fmt.Printf("Error following logs: %v\n", err)
				return nil
			}
		} else {
			fmt.Printf("💡 To view logs, run: qwexctl logs -f %s\n", runID)
		}

		return nil
	},
}

func init() {
	rootCmd.AddCommand(batchCmd)
	batchCmd.Flags().BoolVarP(&follow, "follow", "f", false, "Follow job logs after submission")
	batchCmd.Flags().StringVarP(&batchName, "job", "j", "job", "Job name prefix")
	batchCmd.Flags().StringVarP(&image, "image", "i", "", "Container image to use (default: uv alpine or whatever that full name is idk)")
}
