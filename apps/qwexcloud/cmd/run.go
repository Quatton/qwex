/*
Copyright © 2025 NAME HERE <EMAIL ADDRESS>
*/
package cmd

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"

	"github.com/quatton/qwex/pkg/db"
	"github.com/quatton/qwex/pkg/qapi"
	"github.com/quatton/qwex/pkg/qapi/config"
	"github.com/quatton/qwex/pkg/qapi/routes"
	"github.com/quatton/qwex/pkg/qapi/services"
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
	ctx := context.Background()
	cfg, err := config.ValidateEnv()
	if err != nil {
		log.Fatalf("❌ %v\n", err)
	}

	cfg.Print(log.Printf)

	database, err := db.New(ctx, db.Config{
		Host:     cfg.DBHost,
		Port:     cfg.DBPort,
		User:     cfg.DBUser,
		Password: cfg.DBPassword,
		Database: cfg.DBName,
		SSLMode:  cfg.DBSSLMode,
	})
	if err != nil {
		log.Fatalf("failed to initialize database: %v", err)
	}
	defer database.Close()

	svcs, err := services.NewServices(cfg, database)
	if err != nil {
		log.Fatalf("failed to initialize services: %v", err)
	}

	api := qapi.NewApi()
	routes.RegisterAPI(api.Api, svcs)

	addr := fmt.Sprintf(":%s", cfg.Port)

	log.Printf("🚀 Controller starting on %s\n", addr)
	log.Printf("📚 OpenAPI docs: %s/docs\n", cfg.BaseURL)
	log.Printf("📄 OpenAPI spec: %s/openapi.json\n", cfg.BaseURL)
	log.Printf("🔐 Auth endpoints:\n")

	log.Printf("   - Authorize: %s/api/auth/login", cfg.BaseURL)

	if err := http.ListenAndServe(addr, api.Router); err != nil {
		fmt.Fprintf(os.Stderr, "Server error: %v\n", err)
		os.Exit(1)
	}
}
