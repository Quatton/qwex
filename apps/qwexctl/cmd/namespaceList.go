package cmd

import (
	"fmt"

	"github.com/spf13/cobra"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

var namespaceListCmd = &cobra.Command{
	Use:   "list",
	Short: "List all available namespaces",
	Run: func(cmd *cobra.Command, args []string) {
		service := cmd.Context().Value("service").(*Service)
		res, err := service.K8s.Clientset.CoreV1().Namespaces().List(cmd.Context(), metav1.ListOptions{})

		if err != nil {
			fmt.Printf("Error listing namespaces: %v\n", err)
			return
		}

		for _, ns := range res.Items {
			fmt.Println(ns.Name)
		}
	},
}

func init() {
	namespaceCmd.AddCommand(namespaceListCmd)
}
