package migrations

import (
	"context"
	"fmt"

	"github.com/uptrace/bun"
)

func init() {
	Migrations.MustRegister(func(ctx context.Context, db *bun.DB) error {
		fmt.Print(" [up migration] ")

		_, err := db.NewRaw("CREATE UNIQUE INDEX IF NOT EXISTS auth_refresh_tokens_token_hash_idx ON auth.refresh_tokens (token_hash)").Exec(ctx)
		return err
	}, func(ctx context.Context, db *bun.DB) error {
		fmt.Print(" [down migration] ")

		_, err := db.NewRaw("DROP INDEX IF EXISTS auth_refresh_tokens_token_hash_idx").Exec(ctx)
		return err
	})
}
