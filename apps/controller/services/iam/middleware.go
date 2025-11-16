package iam

import (
	"log"

	"github.com/danielgtaylor/huma/v2"
	"github.com/danielgtaylor/huma/v2/adapters/humachi"
	"github.com/go-pkgz/auth/token"
	"github.com/quatton/qwex/apps/controller/schemas"
)

func (s *IAMService) Middleware() func(ctx huma.Context, next func(huma.Context)) {
	return func(ctx huma.Context, next func(huma.Context)) {
		r, _ := humachi.Unwrap(ctx)
		if tknuser, err := token.GetUserInfo(r); err == nil {
			log.Printf("ℹ Authenticated user: %s", tknuser.SliceAttr("emails"))
			ctx = huma.WithValue(ctx, principalKey, &schemas.User{
				ID:    tknuser.ID,
				Login: tknuser.StrAttr("login"),
				Name:  tknuser.Name,
				Email: tknuser.Email,
			})
		}
		next(ctx)
	}
}
