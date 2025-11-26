package services

import (
	"context"

	"github.com/quatton/qwex/pkg/kv"
	"github.com/quatton/qwex/pkg/qapi/config"
	"github.com/quatton/qwex/pkg/qapi/services/authconfig"
	"github.com/quatton/qwex/pkg/qapi/services/iam"
	"github.com/quatton/qwex/pkg/qart"
	"github.com/quatton/qwex/pkg/qlog"
	"github.com/quatton/qwex/pkg/qrunner"
	"github.com/uptrace/bun"
)

type Services struct {
	Auth    *authconfig.AuthService
	IAM     *iam.IAMService
	Runners *RunnerRegistry
	S3      qart.Store
}

// RunnerRegistry holds runners for each enabled backend
type RunnerRegistry struct {
	Local  qrunner.Runner
	Docker qrunner.Runner
	K8s    qrunner.Runner
}

// Get returns the runner for the specified backend, or nil if not enabled
func (r *RunnerRegistry) Get(backend string) qrunner.Runner {
	switch backend {
	case "local":
		return r.Local
	case "docker":
		return r.Docker
	case "k8s":
		return r.K8s
	default:
		return nil
	}
}

// EnabledBackends returns the list of enabled backend names
func (r *RunnerRegistry) EnabledBackends() []string {
	var backends []string
	if r.Local != nil {
		backends = append(backends, "local")
	}
	if r.Docker != nil {
		backends = append(backends, "docker")
	}
	if r.K8s != nil {
		backends = append(backends, "k8s")
	}
	return backends
}

func NewServices(cfg *config.EnvConfig, db *bun.DB, kvStore kv.Store) (*Services, error) {
	logger := qlog.NewDefault()

	authSvc := authconfig.NewAuthService(cfg, db, kvStore)
	iamSvc := iam.NewIAMService(authSvc)

	// Initialize S3 storage if enabled
	var s3Store qart.Store
	if cfg.S3Enabled {
		store, err := qart.NewS3Store(qart.S3Config{
			Endpoint:  cfg.S3Endpoint,
			AccessKey: cfg.S3AccessKey,
			SecretKey: cfg.S3SecretKey,
			Bucket:    cfg.S3Bucket,
			Region:    cfg.S3Region,
			UseSSL:    cfg.S3UseSSL,
		})
		if err != nil {
			logger.Warn("failed to initialize S3 storage, continuing without it", "error", err)
		} else {
			// Ensure bucket exists
			if err := store.EnsureBucket(context.Background()); err != nil {
				logger.Warn("failed to ensure S3 bucket exists", "error", err)
			} else {
				s3Store = store
				logger.Info("S3 storage initialized", "bucket", cfg.S3Bucket)
			}
		}
	}

	// Create runners for each enabled backend
	runners := &RunnerRegistry{}

	for _, backend := range cfg.EnabledBackends() {
		switch backend {
		case "local":
			opts := []qrunner.LocalRunnerOption{}
			if cfg.RunnerDataDir != "" {
				opts = append(opts, qrunner.WithBaseDir(cfg.RunnerDataDir))
			}
			if s3Store != nil {
				opts = append(opts, qrunner.WithArtifactStore(s3Store))
			}
			runners.Local = qrunner.NewLocalRunner(opts...)
			logger.Info("runner enabled: local")

		case "docker":
			opts := []qrunner.DockerRunnerOption{}
			if s3Store != nil {
				opts = append(opts, qrunner.WithDockerArtifactStore(s3Store))
			}
			dockerRunner, err := qrunner.NewDockerRunner(qrunner.ContainerConfig{}, opts...)
			if err != nil {
				logger.Warn("failed to create docker runner", "error", err)
			} else {
				runners.Docker = dockerRunner
				logger.Info("runner enabled: docker")
			}

		case "k8s":
			// K8s runner needs more config - skip for now if not configured
			logger.Warn("k8s runner not yet supported in this version")
		}
	}

	return &Services{
		Auth:    authSvc,
		IAM:     iamSvc,
		Runners: runners,
		S3:      s3Store,
	}, nil
}

func EmptyServices() *Services {
	return &Services{
		Auth:    nil,
		IAM:     nil,
		Runners: nil,
		S3:      nil,
	}
}
