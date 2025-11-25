package services

import (
	"github.com/quatton/qwex/pkg/kv"
	"github.com/quatton/qwex/pkg/qapi/config"
	"github.com/quatton/qwex/pkg/qapi/services/authconfig"
	"github.com/quatton/qwex/pkg/qapi/services/iam"
	"github.com/quatton/qwex/pkg/qrunner"
	"github.com/uptrace/bun"
)

type Services struct {
	Auth      *authconfig.AuthService
	IAM       *iam.IAMService
	JobRunner qrunner.Runner
}

func NewServices(cfg *config.EnvConfig, db *bun.DB, kvStore kv.Store) (*Services, error) {
	authSvc := authconfig.NewAuthService(cfg, db, kvStore)
	iamSvc := iam.NewIAMService(authSvc)

	// Create Kubernetes runner
	jobRunner, err := qrunner.NewK8sRunner(cfg.K8sNamespace, cfg.K8sQueue, cfg.K8sImage)
	if err != nil {
		return nil, err
	}

	return &Services{
		Auth:      authSvc,
		IAM:       iamSvc,
		JobRunner: jobRunner,
	}, nil
}

func EmptyServices() *Services {
	return &Services{
		Auth:      nil,
		IAM:       nil,
		JobRunner: nil,
	}
}
