package config

import (
	"fmt"
	"log"
	"net/url"
	"strings"

	"github.com/joho/godotenv"
	"github.com/kelseyhightower/envconfig"
	"github.com/quatton/qwex/pkg/qapi/utils"
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
	AccessTokenTTL      int    `envconfig:"ACCESS_TOKEN_TTL" default:"3600"`
	DBHost              string `envconfig:"DB_HOST" default:"localhost"`
	DBPort              int    `envconfig:"DB_PORT" default:"5432"`
	DBUser              string `envconfig:"DB_USER" default:"qwex"`
	DBPassword          string `envconfig:"DB_PASSWORD" default:"password"`
	DBName              string `envconfig:"DB_NAME" default:"qwex"`
	DBSSLMode           string `envconfig:"DB_SSLMODE" default:"disable"`
	RefreshTokenTTL     int    `envconfig:"REFRESH_TOKEN_TTL" default:"2592000"` // 30 days
}

func ValidateEnv() (*EnvConfig, error) {
	if utils.IsDev() {
		if err := godotenv.Load(); err != nil {
			log.Println("ℹ No .env file found")
		} else {
			log.Println("✓ Loaded .env file")
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
	fmtr("  Refresh TTL: %ds\n", c.RefreshTokenTTL)

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
