package iam

import (
	"log"
	"strings"

	"github.com/danielgtaylor/huma/v2"
	"github.com/danielgtaylor/huma/v2/adapters/humachi"
)

func (s *IAMService) Middleware() func(ctx huma.Context, next func(huma.Context)) {
	return func(ctx huma.Context, next func(huma.Context)) {
		r, _ := humachi.Unwrap(ctx)

		authHeader := r.Header.Get("Authorization")
		if authHeader != "" {
			parts := strings.SplitN(authHeader, " ", 2)
			if len(parts) == 2 && parts[0] == "Bearer" {
				token := parts[1]
				if user, err := s.auth.ValidateToken(token); err == nil {
					log.Printf("ℹ Authenticated user: %s (%s)", user.Login, user.Email)
					ctx = huma.WithValue(ctx, principalKey, user)
				} else {
					log.Printf("⚠️ Invalid token: %v", err)
				}
			}
		}

		next(ctx)
	}
}
