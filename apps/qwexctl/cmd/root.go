package cmd

import (
	"os"

	"github.com/spf13/cobra"
)

var rootCmd = &cobra.Command{
	Use:   "qwexctl",
	Short: "Queued Workspace-aware EXecutor",
	Long:  `qwexctl - A thin (?) wrapper around a Kubernetes cluster to provide a local-remote development platform that focuses on stateless workloads.`,
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
