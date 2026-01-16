package cmd

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"time"

	"github.com/Quatton/qwex/apps/qwexctl/internal/connect"
	"github.com/Quatton/qwex/apps/qwexctl/internal/pods"
	"github.com/spf13/cobra"
)

var execCmd = &cobra.Command{
	Use:   "exec -- [command]",
	Short: "Execute a command on the remote workspace (Syncs first)",
	// This allows the user to pass flags like '-it' intended for kubectl
	// without defining them in Cobra.
	DisableFlagParsing: true,
	RunE: func(cmd *cobra.Command, args []string) error {

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

		localRepoPath := connect.GetLocalRepoPath(cfgFile)

		connectService := connect.NewService(svc.K8s.Clientset, svc.K8s.Config, namespace, pod.Name, pods.SyncContainerName, localRepoPath)

		ctx, cancel := context.WithCancel(cmd.Context())
		defer cancel()

		go func() {
			ticker := time.NewTicker(2 * time.Second)
			defer ticker.Stop()

			for {
				select {
				case <-ctx.Done():
					return
				case <-ticker.C:
					if err := connectService.SyncOnce(ctx); err != nil {
					}
				}
			}
		}()

		if err := connectService.SyncOnce(ctx); err != nil {
			return fmt.Errorf("pre-execution sync failed: %w", err)
		}

		kubectlArgs := []string{"exec", "-i", "-t"}
		kubectlArgs = append(kubectlArgs, "-n", svc.Namespace)
		kubectlArgs = append(kubectlArgs, pod.Name)
		kubectlArgs = append(kubectlArgs, "-c", pods.DevContainerName)
		kubectlArgs = append(kubectlArgs, args...)

		fmt.Printf("🚀 Connecting to %s...\n", pod.Name)

		child := exec.Command("kubectl", kubectlArgs...)

		child.Stdin = os.Stdin
		child.Stdout = os.Stdout
		child.Stderr = os.Stderr

		if err := child.Run(); err != nil {
			return err
		}

		return nil
	},
}

func init() {
	rootCmd.AddCommand(execCmd)
}
