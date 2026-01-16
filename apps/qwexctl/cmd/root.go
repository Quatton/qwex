package cmd

import (
	"context"
	"os"

	"github.com/Quatton/qwex/apps/qwexctl/internal/k8s"
	"github.com/spf13/cobra"
)

type Service struct {
	K8s *k8s.K8sClient
}

var rootCmd = &cobra.Command{
	Use:   "qwexctl",
	Short: "Queued Workspace-aware EXecutor",
	Long:  `qwexctl - A thin (?) wrapper around a Kubernetes cluster to provide a local-remote development platform that focuses on stateless workloads.`,
	PersistentPreRunE: func(cmd *cobra.Command, args []string) error {

		var GlobalService = &Service{}

		k8sClient, err := k8s.NewK8sClient()
		if err != nil {
			return err
		}
		GlobalService.K8s = k8sClient
		ctx := context.WithValue(cmd.Context(), "service", GlobalService)
		cmd.SetContext(ctx)
		return nil

	},
}

func Execute() {
	err := rootCmd.Execute()
	if err != nil {
		os.Exit(1)
	}
}

func init() {
	cobra.OnInitialize(initConfig)
}

func initConfig() {

}
