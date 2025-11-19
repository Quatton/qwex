package cmd

import (
	"fmt"

	"github.com/spf13/cobra"
)

var authCmd = &cobra.Command{
	Use:   "auth",
	Short: "Manage authentication with the qwex controller (login, logout, status)",
	Long: `Manage authentication against a running qwex controller.

Subcommands will let you obtain tokens (login), invalidate them (logout),
and inspect the current authentication status. Tokens are stored in the
local environment or config directory for use by other qwexctl commands.

Examples:
  qwexctl auth login
  qwexctl auth logout
  qwexctl auth status`,
	Run: func(cmd *cobra.Command, args []string) {
		fmt.Println("auth called")
	},
}

func init() {
	rootCmd.AddCommand(authCmd)
}
