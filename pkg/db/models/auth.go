package models

import (
	"time"

	"github.com/google/uuid"
	"github.com/uptrace/bun"
)

type User struct {
	bun.BaseModel `bun:"table:auth.users,alias:u"`

	ID        uuid.UUID `bun:"type:uuid,default:gen_random_uuid(),pk"`
	Email     string    `bun:",unique,notnull"`
	CreatedAt time.Time `bun:",nullzero,notnull,default:current_timestamp"`
	UpdatedAt time.Time `bun:",nullzero,notnull,default:current_timestamp"`
}

type RefreshToken struct {
	bun.BaseModel `bun:"table:auth.refresh_tokens,alias:rt"`

	ID        uuid.UUID `bun:"type:uuid,default:gen_random_uuid(),pk"`
	UserID    uuid.UUID `bun:"type:uuid,notnull"`
	TokenHash string    `bun:",notnull"`
	ExpiresAt time.Time `bun:",notnull"`
	CreatedAt time.Time `bun:",nullzero,notnull,default:current_timestamp"`

	// Relations
	User *User `bun:"rel:belongs-to,join:user_id=id"`
}
