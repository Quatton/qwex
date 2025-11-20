package iam

import (
	"strings"

	"github.com/danielgtaylor/huma/v2"
	"github.com/danielgtaylor/huma/v2/adapters/humachi"
	"github.com/quatton/qwex/pkg/qlog"
)

func (s *IAMService) Middleware() func(ctx huma.Context, next func(huma.Context)) {
	logger := qlog.NewDefault()

	return func(ctx huma.Context, next func(huma.Context)) {
		r, _ := humachi.Unwrap(ctx)

		authHeader := r.Header.Get("Authorization")
		if authHeader != "" {
			parts := strings.SplitN(authHeader, " ", 2)
			if len(parts) == 2 && parts[0] == "Bearer" {
				token := parts[1]
				if user, err := s.auth.ValidateToken(token); err == nil {
					logger.Debug("authenticated user", "login", user.Login, "email", user.Email)
					ctx = huma.WithValue(ctx, principalKey, user)
				} else {
					logger.Warn("invalid token", "error", err)
				}
			}
		}

		next(ctx)
	}
}
