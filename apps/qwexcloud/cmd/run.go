/*
Copyright © 2025 NAME HERE <EMAIL ADDRESS>
*/
package cmd

import (
	"context"
	"fmt"
	"net/http"

	"github.com/quatton/qwex/pkg/db"
	"github.com/quatton/qwex/pkg/qapi"
	"github.com/quatton/qwex/pkg/qapi/config"
	"github.com/quatton/qwex/pkg/qapi/routes"
	"github.com/quatton/qwex/pkg/qapi/services"
	"github.com/quatton/qwex/pkg/qlog"
	"github.com/spf13/cobra"
)

// runCmd represents the run command
var runCmd = &cobra.Command{
	Use:   "run",
	Short: "A brief description of your command",
	Long: `A longer description that spans multiple lines and likely contains examples
and usage of using your command. For example:

Cobra is a CLI library for Go that empowers applications.
This application is a tool to generate the needed files
to quickly create a Cobra application.`,
	Run: run,
}

func init() {
	rootCmd.AddCommand(runCmd)
}

func run(cmd *cobra.Command, args []string) {
	logger := qlog.NewDefault()
	ctx := context.Background()

	cfg, err := config.ValidateEnv()
	if err != nil {
		logger.Fatal("failed to validate environment", "error", err)
	}

	cfg.Print(func(format string, args ...any) {
		logger.Info(fmt.Sprintf(format, args...))
	})

	database, err := db.New(ctx, db.Config{
		Host:     cfg.DBHost,
		Port:     cfg.DBPort,
		User:     cfg.DBUser,
		Password: cfg.DBPassword,
		Database: cfg.DBName,
		SSLMode:  cfg.DBSSLMode,
	})
	if err != nil {
		logger.Fatal("failed to initialize database", "error", err)
	}
	defer database.Close()

	svcs, err := services.NewServices(cfg, database)
	if err != nil {
		logger.Fatal("failed to initialize services", "error", err)
	}

	api := qapi.NewApi()
	routes.RegisterAPI(api.Api, svcs)

	addr := fmt.Sprintf(":%s", cfg.Port)

	logger.Info("controller starting", "addr", addr)
	logger.Info("openapi docs", "url", fmt.Sprintf("%s/docs", cfg.BaseURL))
	logger.Info("openapi spec", "url", fmt.Sprintf("%s/openapi.json", cfg.BaseURL))
	logger.Info("auth endpoints")
	logger.Info("  authorize endpoint", "url", fmt.Sprintf("%s/api/auth/login", cfg.BaseURL))

	if err := http.ListenAndServe(addr, api.Router); err != nil {
		logger.Fatal("server error", "error", err)
	}
}
