package cmd

import (
	"fmt"

	"github.com/spf13/cobra"
)

var namespaceListCmd = &cobra.Command{
	Use:   "list",
	Short: "List all available namespaces",
	Long:  "List all available namespaces",
	Run: func(cmd *cobra.Command, args []string) {
		// TODO: Our demo only has one namespace :)
		fmt.Println("qwex-demo")
	},
}

func init() {
	namespaceCmd.AddCommand(namespaceListCmd)
}
