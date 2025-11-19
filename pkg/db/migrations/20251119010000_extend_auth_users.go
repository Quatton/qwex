package migrations

import (
	"context"
	"fmt"

	"github.com/uptrace/bun"
)

func init() {
	Migrations.MustRegister(func(ctx context.Context, db *bun.DB) error {
		fmt.Print(" [up migration] ")

		stmts := []string{
			"ALTER TABLE auth.users ADD COLUMN IF NOT EXISTS login TEXT NOT NULL DEFAULT ''",
			"ALTER TABLE auth.users ADD COLUMN IF NOT EXISTS name TEXT",
			"ALTER TABLE auth.users ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'github'",
			"ALTER TABLE auth.users ADD COLUMN IF NOT EXISTS provider_id TEXT NOT NULL DEFAULT ''",
			"CREATE UNIQUE INDEX IF NOT EXISTS auth_users_provider_provider_id_idx ON auth.users (provider, provider_id)",
		}

		for _, stmt := range stmts {
			if _, err := db.NewRaw(stmt).Exec(ctx); err != nil {
				return err
			}
		}

		return nil
	}, func(ctx context.Context, db *bun.DB) error {
		fmt.Print(" [down migration] ")

		stmts := []string{
			"DROP INDEX IF EXISTS auth_users_provider_provider_id_idx",
			"ALTER TABLE auth.users DROP COLUMN IF EXISTS provider_id",
			"ALTER TABLE auth.users DROP COLUMN IF EXISTS provider",
			"ALTER TABLE auth.users DROP COLUMN IF EXISTS name",
			"ALTER TABLE auth.users DROP COLUMN IF EXISTS login",
		}

		for _, stmt := range stmts {
			if _, err := db.NewRaw(stmt).Exec(ctx); err != nil {
				return err
			}
		}

		return nil
	})
}
