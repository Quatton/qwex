package cmd

import (
	"fmt"

	"github.com/Quatton/qwex/apps/qwexctl/internal/connect"
	"github.com/Quatton/qwex/apps/qwexctl/internal/pods"
	"github.com/Quatton/qwex/apps/qwexctl/internal/utils"
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

		if err := connectService.SyncOnce(ctx); err != nil {
			return fmt.Errorf("pre-execution sync failed: %w", err)
		}

		kubectlArgs := []string{"kubectl", "exec", "-i", "-t"}
		kubectlArgs = append(kubectlArgs, "-n", svc.Namespace)
		kubectlArgs = append(kubectlArgs, pod.Name)
		kubectlArgs = append(kubectlArgs, "-c", pods.DevContainerName)
		kubectlArgs = append(kubectlArgs, args...)

		fmt.Printf("🚀 Connecting to %s...\n", pod.Name)
		return utils.ReplaceProcess("kubectl", kubectlArgs)
	},
}

func init() {
	rootCmd.AddCommand(execCmd)
}
