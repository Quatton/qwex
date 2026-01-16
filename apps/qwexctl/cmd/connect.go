package cmd

import (
	"github.com/Quatton/qwex/apps/qwexctl/internal/pods"
	"github.com/spf13/cobra"
)

var connectCmd = &cobra.Command{
	Use:   "connect",
	Short: "Connect to a development instance",
	Long:  "Connect to a development instance",
	Run: func(cmd *cobra.Command, args []string) {
		service := cmd.Context().Value("service").(*Service)
		podService := pods.NewService(service.K8s)

		namespace := args[0]

		podService.GetOrCreateDevelopmentDeployment(cmd.Context(), namespace)
	},
}

func init() {

	rootCmd.AddCommand(connectCmd)
}
