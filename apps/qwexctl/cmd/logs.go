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

var followLogs bool

var logsCmd = &cobra.Command{
	Use:   "logs [run-id]",
	Short: "View logs for a batch job run",
	Long: `View logs for a specific batch job run by its run-id.
Use -f/--follow to stream logs in real-time.`,
	Args: cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		runID := args[0]

		localRepoPath := connect.GetLocalRepoPath(cfgFile)

		svc, err := initServiceManual()
		if err != nil {
			return err
		}
		ctx := cmd.Context()

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

		batchService := batch.NewService(connectService, "", "", nil, nil, "", "")

		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
		defer cancel()

		if followLogs {
			fmt.Printf("📋 Following logs for run: %s\n", runID)
			if err := batchService.FollowRunLogs(ctx, runID, os.Stdout); err != nil {
				return fmt.Errorf("failed to follow logs: %w", err)
			}
		} else {
			fmt.Printf("📋 Fetching logs for run: %s\n", runID)
			logs, err := batchService.GetRunLogs(ctx, runID)
			if err != nil {
				return fmt.Errorf("failed to get logs: %w", err)
			}
			fmt.Print(logs)
		}

		return nil
	},
}

func init() {
	rootCmd.AddCommand(logsCmd)
	logsCmd.Flags().BoolVarP(&followLogs, "follow", "f", false, "Follow log output in real-time")
}
