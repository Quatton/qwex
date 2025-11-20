package db

import (
	"context"
	"fmt"

	"github.com/quatton/qwex/pkg/db/migrations"
	"github.com/quatton/qwex/pkg/qlog"
	"github.com/uptrace/bun"
	"github.com/uptrace/bun/migrate"
)

// Migrate runs the database migrations.
func Migrate(ctx context.Context, db *bun.DB) error {
	logger := qlog.NewDefault()
	migrator := migrate.NewMigrator(db, migrations.Migrations)

	// Initialize the migration tables if they don't exist
	if err := migrator.Init(ctx); err != nil {
		return fmt.Errorf("failed to init migrations: %w", err)
	}

	// Check if there are any pending migrations
	group, err := migrator.Migrate(ctx)
	if err != nil {
		return fmt.Errorf("failed to migrate: %w", err)
	}

	if group.ID == 0 {
		logger.Info("database is up to date")
		return nil
	}

	logger.Info("migrated", "group", group.String())
	return nil
}
