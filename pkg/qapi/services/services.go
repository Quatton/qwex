package services

import (
	"github.com/quatton/qwex/pkg/qapi/config"
	"github.com/quatton/qwex/pkg/qapi/services/authconfig"
	"github.com/quatton/qwex/pkg/qapi/services/iam"
	"github.com/uptrace/bun"
)

type Services struct {
	Auth *authconfig.AuthService
	IAM  *iam.IAMService
}

func NewServices(cfg *config.EnvConfig, db *bun.DB) (*Services, error) {
	authSvc := authconfig.NewAuthService(cfg, db)
	iamSvc := iam.NewIAMService(authSvc)

	return &Services{
		Auth: authSvc,
		IAM:  iamSvc,
	}, nil
}

func EmptyServices() *Services {
	return &Services{
		Auth: nil,
		IAM:  nil,
	}
}
