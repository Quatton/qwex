package cmd

import (
	"context"
	"errors"
	"os"

	"github.com/quatton/qwex/pkg/qsdk"
	"github.com/spf13/cobra"
)

type contextKey string

const configContextKey contextKey = "qwexconfig"

var (
	cfgFile string
	rootCmd = &cobra.Command{
		Use:   "qwexctl",
		Short: "CLI for interacting with the qwex controller (auth, machines, health)",
		Long: `qwexctl is a small command-line tool for interacting with a running
qwex controller API. It provides subcommands to authenticate, inspect your
machines, start/stop machines, and check controller health. Use the
auth subcommands to obtain and manage tokens; use machines to list/create/delete
machines; and use health to validate the controller is reachable.`,
		PersistentPreRunE: func(cmd *cobra.Command, args []string) error {
			cfg, err := qsdk.LoadConfig(cfgFile)
			if err != nil {
				return err
			}

			if err := cfg.Viper().BindPFlags(cmd.Flags()); err != nil {
				return err
			}

			ctx := context.WithValue(cmd.Context(), configContextKey, cfg)
			cmd.SetContext(ctx)

			return nil
		},
	}
)

// GetConfig retrieves the Config from the command context
func GetConfig(cmd *cobra.Command) (*qsdk.Config, error) {
	ctx := cmd.Context()
	cfg, ok := ctx.Value(configContextKey).(*qsdk.Config)
	if !ok {
		return nil, errors.New("no config in context")
	}
	return cfg, nil
}

func Execute() {
	err := rootCmd.Execute()
	if err != nil {
		os.Exit(1)
	}
}

func init() {
	rootCmd.PersistentFlags().StringVar(&cfgFile, "config", "", "config file (YAML). Searches: qwex.yaml, .qwex/config.yaml, $XDG_CONFIG_HOME/qwex, $HOME/.config/qwex")
	rootCmd.PersistentFlags().String("base-url", "", "Base URL for the qwex controller (overrides config)")
	rootCmd.Flags().BoolP("toggle", "t", false, "Help message for toggle")
}
