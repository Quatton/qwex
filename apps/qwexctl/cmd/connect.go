package cmd

import (
	"fmt"

	"github.com/spf13/cobra"
)

var connectCmd = &cobra.Command{
	Use:   "connect",
	Short: "Connect to a development instance",
	Long:  "Connect to a development instance",
	Run: func(cmd *cobra.Command, args []string) {
		fmt.Println("connect called")
	},
}

func init() {
	rootCmd.AddCommand(connectCmd)
}
