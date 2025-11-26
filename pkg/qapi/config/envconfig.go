package config

import (
	"fmt"
	"net/url"
	"strings"

	"github.com/joho/godotenv"
	"github.com/kelseyhightower/envconfig"
	"github.com/quatton/qwex/pkg/qapi/utils"
	"github.com/quatton/qwex/pkg/qlog"
)

type EnvConfig struct {
	Port                string `envconfig:"PORT" default:"3000"`
	BaseURL             string `envconfig:"BASE_URL" required:"true"`
	AuthSecret          string `envconfig:"AUTH_SECRET" required:"true"`
	GitHubAppID         int64  `envconfig:"GITHUB_APP_ID"`
	GitHubAppPrivateKey string `envconfig:"GITHUB_APP_PRIVATE_KEY"`
	GitHubClientID      string `envconfig:"GITHUB_CLIENT_ID"`
	GitHubClientSecret  string `envconfig:"GITHUB_CLIENT_SECRET"`
	Environment         string `envconfig:"ENVIRONMENT" default:"development"`
	AccessTokenTTL      int    `envconfig:"ACCESS_TOKEN_TTL" default:"900"`
	DBHost              string `envconfig:"DB_HOST" default:"localhost"`
	DBPort              int    `envconfig:"DB_PORT" default:"5432"`
	DBUser              string `envconfig:"DB_USER" default:"qwex"`
	DBPassword          string `envconfig:"DB_PASSWORD" default:"password"`
	DBName              string `envconfig:"DB_NAME" default:"qwex"`
	DBSSLMode           string `envconfig:"DB_SSLMODE" default:"disable"`
	RefreshTokenTTL     int    `envconfig:"REFRESH_TOKEN_TTL" default:"2592000"` // 30 days
	// Valkey/Redis configuration
	ValkeyAddr     string `envconfig:"VALKEY_ADDR" default:"localhost:6379"`
	ValkeyPassword string `envconfig:"VALKEY_PASSWORD" default:""`
	ValkeyDB       int    `envconfig:"VALKEY_DB" default:"0"`

	// Runner configuration
	// RunnerEnabledBackends is a comma-separated list of enabled backends (local, docker, k8s)
	// The client chooses which backend to use when submitting a job
	RunnerEnabledBackends string `envconfig:"RUNNER_ENABLED_BACKENDS" default:"local"`
	RunnerDataDir         string `envconfig:"RUNNER_DATA_DIR" default:".qwex/runs"`

	// S3-compatible storage configuration (e.g., MinIO)
	S3Enabled   bool   `envconfig:"S3_ENABLED" default:"true"`
	S3Endpoint  string `envconfig:"S3_ENDPOINT" default:"localhost:9000"`
	S3Bucket    string `envconfig:"S3_BUCKET" default:"qwex-artifacts"`
	S3AccessKey string `envconfig:"S3_ACCESS_KEY" default:"minioadmin"`
	S3SecretKey string `envconfig:"S3_SECRET_KEY" default:"minioadmin"`
	S3UseSSL    bool   `envconfig:"S3_USE_SSL" default:"false"`
	S3Region    string `envconfig:"S3_REGION" default:"us-east-1"`

	// Allowed redirect URIs (comma-separated prefixes)
	AllowedRedirects string `envconfig:"ALLOWED_REDIRECTS" default:"http://localhost"`
}

func ValidateEnv() (*EnvConfig, error) {
	logger := qlog.NewDefault()

	if utils.IsDev() {
		if err := godotenv.Load(); err != nil {
			logger.Info("no .env file found")
		} else {
			logger.Info("loaded .env file")
		}
	}

	var cfg EnvConfig
	if err := envconfig.Process("", &cfg); err != nil {
		return nil, fmt.Errorf("failed to load environment variables: %w", err)
	}

	var errors []string

	if len(cfg.AuthSecret) < 32 {
		errors = append(errors, "  ❌ AUTH_SECRET must be at least 32 characters")
	}

	if cfg.GitHubAppID != 0 && cfg.GitHubAppPrivateKey == "" {
		errors = append(errors, "  ❌ GITHUB_APP_PRIVATE_KEY is required when GITHUB_APP_ID is set")
	}

	if (cfg.GitHubClientID != "" && cfg.GitHubClientSecret == "") || (cfg.GitHubClientID == "" && cfg.GitHubClientSecret != "") {
		errors = append(errors, "  ❌ Both GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET must be set together")
	}

	if _, err := url.ParseRequestURI(cfg.BaseURL); err != nil {
		errors = append(errors, "  ❌ BASE_URL must be a valid URL")
	}

	if len(errors) > 0 {
		return nil, fmt.Errorf("environment validation failed:\n%s", strings.Join(errors, "\n"))
	}

	return &cfg, nil
}

func MaskSecret(secret string) string {
	if secret == "" {
		return "<not set>"
	}
	if len(secret) <= 8 {
		return "***"
	}
	return secret[:4] + "..." + secret[len(secret)-4:]
}

func (c *EnvConfig) Print(fmtr func(string, ...interface{})) {
	fmtr("📋 Configuration:\n")
	fmtr("  Environment: %s\n", c.Environment)
	fmtr("  Port: %s\n", c.Port)
	fmtr("  Base URL: %s\n", c.BaseURL)
	fmtr("  Auth Secret: %s\n", MaskSecret(c.AuthSecret))
	fmtr("  Database: %s@%s:%d/%s (sslmode=%s)\n", c.DBUser, c.DBHost, c.DBPort, c.DBName, c.DBSSLMode)
	fmtr("  Valkey: %s (db=%d)\n", c.ValkeyAddr, c.ValkeyDB)
	fmtr("  Access Token TTL: %ds\n", c.AccessTokenTTL)
	fmtr("  Refresh Token TTL: %ds\n", c.RefreshTokenTTL)
	fmtr("  Allowed Redirects: %s\n", c.AllowedRedirects)

	// Runner configuration
	fmtr("  Runner Enabled Backends: %s\n", c.RunnerEnabledBackends)
	fmtr("  Runner Data Dir: %s\n", c.RunnerDataDir)

	// S3 storage
	if c.S3Enabled {
		fmtr("  S3: ✓ Enabled\n")
		fmtr("    Endpoint: %s\n", c.S3Endpoint)
		fmtr("    Bucket: %s\n", c.S3Bucket)
		fmtr("    SSL: %v\n", c.S3UseSSL)
	} else {
		fmtr("  S3: ✗ Disabled\n")
	}

	if c.GitHubAppID != 0 {
		fmtr("  GitHub App: ✓ Enabled (ID: %d)\n", c.GitHubAppID)
	} else {
		fmtr("  GitHub App: ✗ Disabled\n")
	}

	if c.GitHubClientID != "" {
		fmtr("  GitHub OAuth: ✓ Enabled\n")
		fmtr("    Client ID: %s\n", MaskSecret(c.GitHubClientID))
		fmtr("    Client Secret: %s\n", MaskSecret(c.GitHubClientSecret))
	} else {
		fmtr("  GitHub OAuth: ✗ Disabled\n")
	}
}

// EnabledBackends returns the list of enabled runner backends
func (c *EnvConfig) EnabledBackends() []string {
	if c.RunnerEnabledBackends == "" {
		return []string{}
	}
	backends := strings.Split(c.RunnerEnabledBackends, ",")
	result := make([]string, 0, len(backends))
	for _, b := range backends {
		b = strings.TrimSpace(b)
		if b != "" {
			result = append(result, b)
		}
	}
	return result
}

// IsBackendEnabled checks if a specific backend is enabled
func (c *EnvConfig) IsBackendEnabled(backend string) bool {
	for _, b := range c.EnabledBackends() {
		if b == backend {
			return true
		}
	}
	return false
}
