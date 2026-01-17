package cmd

import (
	"fmt"

	"github.com/Quatton/qwex/apps/qwexctl/internal/connect"
	"github.com/Quatton/qwex/apps/qwexctl/internal/pods"
	"github.com/spf13/cobra"
)

var connectCmd = &cobra.Command{
	Use:   "sync",
	Short: "Sync local code to the development pod",
	Run: func(cmd *cobra.Command, args []string) {
		service := cmd.Context().Value("service").(*Service)
		namespace := cmd.Flag("namespace").Value.String()
		podService := pods.NewService(service.K8s.Clientset, namespace)

		dep, err := podService.GetOrCreateDevelopmentDeployment(cmd.Context(), pods.Active)
		if err != nil {
			fmt.Printf("Error getting or creating development deployment: %v\n", err)
			return
		}

		pod, err := podService.GetPodFromDeployment(cmd.Context(), dep)

		if err != nil {
			fmt.Printf("Error getting pod from deployment: %v\n", err)
			return
		}

		localRepoPath := connect.GetLocalRepoPath(cmd.Flag("config").Value.String())

		connectService := connect.NewService(service.K8s.Clientset, service.K8s.Config, namespace, pod.Name, pods.SyncContainerName, localRepoPath)

		err = connectService.SyncOnce(cmd.Context())
		if err != nil && err.Error() != "up_to_date" {
			fmt.Printf("Error during sync: %v\n", err)
			return
		}

		fmt.Println("Sync completed successfully.")
	},
}

func init() {
	rootCmd.AddCommand(connectCmd)
}
