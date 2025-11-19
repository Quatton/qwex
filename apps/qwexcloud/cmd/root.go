package cmd

import (
	"os"

	"github.com/spf13/cobra"
)

// rootCmd represents the base command when called without any subcommands
var rootCmd = &cobra.Command{
	Use:   "qloud",
	Short: "Qwex Cloud CLI",
	Long:  `Qwex Cloud CLI is a command-line interface for managing Qwex Cloud resources.`,
}

func Execute() {
	err := rootCmd.Execute()
	if err != nil {
		os.Exit(1)
	}
}

func init() {
}
