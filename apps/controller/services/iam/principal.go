package iam

import (
	"context"

	"github.com/quatton/qwex/apps/controller/schemas"
)

type ctxKey string

const principalKey ctxKey = "qwex.principal"

func (s *IAMService) Principal(ctx context.Context) (*schemas.User, bool) {
	if v := ctx.Value(principalKey); v != nil {
		if p, ok := v.(*schemas.User); ok {
			return p, true
		}
	}
	return nil, false
}

func (s *IAMService) Must(ctx context.Context) *schemas.User {
	if p, ok := s.Principal(ctx); ok && p != nil {
		return p
	}
	panic("principal missing in context; ensure IAM middleware is installed and auth performed")
}

func (s *IAMService) Get(ctx context.Context) (*schemas.User, error) {
	if p, ok := s.Principal(ctx); ok && p != nil {
		return p, nil
	}
	return nil, nil
}
