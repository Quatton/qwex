package models

import (
	"time"

	"github.com/google/uuid"
	"github.com/uptrace/bun"
)

type User struct {
	bun.BaseModel `bun:"table:auth.users,alias:u"`

	ID         uuid.UUID `bun:"type:uuid,default:gen_random_uuid(),pk"`
	Email      string    `bun:",unique,notnull"`
	Login      string    `bun:",notnull"`
	Name       string    `bun:",nullzero"`
	Provider   string    `bun:",notnull"`
	ProviderID string    `bun:",notnull"`

	GithubInstallationID int64 `bun:",nullzero"`

	CreatedAt time.Time `bun:",nullzero,notnull,default:current_timestamp"`
	UpdatedAt time.Time `bun:",nullzero,notnull,default:current_timestamp"`
}

// Note: RefreshToken is now stored in Valkey (pkg/kv), not in the database.
