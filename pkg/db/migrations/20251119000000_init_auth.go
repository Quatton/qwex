package migrations

import (
	"context"
	"fmt"

	"github.com/quatton/qwex/pkg/db/models"
	"github.com/uptrace/bun"
)

func init() {
	Migrations.MustRegister(func(ctx context.Context, db *bun.DB) error {
		fmt.Print(" [up migration] ")

		// Create auth schema
		_, err := db.NewRaw("CREATE SCHEMA IF NOT EXISTS auth").Exec(ctx)
		if err != nil {
			return err
		}

		// Create users table from struct
		_, err = db.NewCreateTable().
			Model((*models.User)(nil)).
			IfNotExists().
			Exec(ctx)
		if err != nil {
			return err
		}

		// Create refresh_tokens table from struct
		_, err = db.NewCreateTable().
			Model((*models.RefreshToken)(nil)).
			IfNotExists().
			ForeignKey(`("user_id") REFERENCES auth.users ("id") ON DELETE CASCADE`).
			Exec(ctx)
		if err != nil {
			return err
		}

		return nil
	}, func(ctx context.Context, db *bun.DB) error {
		fmt.Print(" [down migration] ")

		_, err := db.NewDropTable().Model((*models.RefreshToken)(nil)).IfExists().Exec(ctx)
		if err != nil {
			return err
		}

		_, err = db.NewDropTable().Model((*models.User)(nil)).IfExists().Exec(ctx)
		if err != nil {
			return err
		}

		_, err = db.NewRaw("DROP SCHEMA IF EXISTS auth").Exec(ctx)
		if err != nil {
			return err
		}

		return nil
	})
}

