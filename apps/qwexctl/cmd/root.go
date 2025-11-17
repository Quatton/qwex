/*
Copyright © 2025 NAME HERE <EMAIL ADDRESS>
*/
package cmd

import (
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
			return qsdk.Initialize(cmd, cfgFile)
		},
	}
)

func GetConfigFromContext(cmd *cobra.Command) (*qsdk.Config, error) {
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
	rootCmd.PersistentFlags().StringVar(&cfgFile, "config", "", "config file (TOML). Searches: ., $XDG_CONFIG_HOME/qwexctl, $HOME/.config/qwexctl, $HOME")
	rootCmd.PersistentFlags().String("base-url", "", "Base URL for the qwex controller (overrides config)")
	rootCmd.Flags().BoolP("toggle", "t", false, "Help message for toggle")
}
