package main

import (
	"context"
	"log"

	"github.com/joho/godotenv"
	"github.com/kelseyhightower/envconfig"
	"github.com/quatton/qwex/pkg/db"
)

func main() {
	if err := godotenv.Load(); err != nil {
		log.Println("ℹ No .env file found")
	} else {
		log.Println("✓ Loaded .env file")
	}

	ctx := context.Background()

	cfg := db.Config{
		Host:     "localhost",
		Port:     5432,
		User:     "qwex",
		Password: "password",
		Database: "qwex",
		SSLMode:  "disable",
	}

	if err := envconfig.Process("DB", &cfg); err != nil {
		log.Fatalf("failed to process env vars: %v", err)
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
