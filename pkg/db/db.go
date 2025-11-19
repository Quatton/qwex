package db

import (
	"context"
	"database/sql"
	"fmt"
	"runtime"

	"github.com/uptrace/bun"
	"github.com/uptrace/bun/dialect/pgdialect"
	"github.com/uptrace/bun/driver/pgdriver"
	"github.com/uptrace/bun/extra/bundebug"
)

type Config struct {
	Host     string
	Port     int
	User     string
	Password string
	Database string
	SSLMode  string
}

func New(ctx context.Context, cfg Config) (*bun.DB, error) {
	dsn := fmt.Sprintf("postgres://%s:%s@%s:%d/%s?sslmode=%s",
		cfg.User, cfg.Password, cfg.Host, cfg.Port, cfg.Database, cfg.SSLMode)

	sqldb := sql.OpenDB(pgdriver.NewConnector(pgdriver.WithDSN(dsn)))

	db := bun.NewDB(sqldb, pgdialect.New())

	// Add a hook to print SQL queries to stdout for debugging
	db.AddQueryHook(bundebug.NewQueryHook(
		bundebug.WithVerbose(true), // log everything
		bundebug.FromEnv("BUNDEBUG"),
	))

	// Verify connection
	if err := db.PingContext(ctx); err != nil {
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}

	// Set reasonable defaults
	maxOpenConns := 4 * runtime.GOMAXPROCS(0)
	db.SetMaxOpenConns(maxOpenConns)
	db.SetMaxIdleConns(maxOpenConns)

	return db, nil
}
