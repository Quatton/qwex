package main

import (
	"context"
	"log"
	"os"

	"github.com/quatton/qwex/pkg/db"
)

func main() {
	ctx := context.Background()

	cfg := db.Config{
		Host:     "localhost",
		Port:     5432,
		User:     "qwex",
		Password: "password",
		Database: "qwex",
		SSLMode:  "disable",
	}

	// Override with env vars if needed
	if host := os.Getenv("DB_HOST"); host != "" {
		cfg.Host = host
	}

	database, err := db.New(ctx, cfg)
	if err != nil {
		log.Fatalf("failed to connect to database: %v", err)
	}
	defer database.Close()

	log.Println("Running migrations...")
	if err := db.Migrate(ctx, database); err != nil {
		log.Fatalf("failed to migrate: %v", err)
	}
	log.Println("Migrations completed successfully.")
}
