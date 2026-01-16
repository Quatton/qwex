package cmd

import (
	"github.com/spf13/cobra"
)

var namespaceCmd = &cobra.Command{
	Use:   "namespace",
	Short: "Subcommand for namespace operations",
	Long:  "Subcommand for namespace operations",
}

func init() {
	rootCmd.AddCommand(namespaceCmd)
}
