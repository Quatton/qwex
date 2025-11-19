package config

import (
	"fmt"
	"log"
	"net/url"
	"strings"

	"github.com/joho/godotenv"
	"github.com/kelseyhightower/envconfig"
	"github.com/quatton/qwex/apps/controller/utils"
)

type EnvConfig struct {
	Port               string `envconfig:"PORT" default:"3000"`
	BaseURL            string `envconfig:"BASE_URL" required:"true"`
	AuthSecret         string `envconfig:"AUTH_SECRET" required:"true"`
	GitHubClientID     string `envconfig:"GITHUB_CLIENT_ID"`
	GitHubClientSecret string `envconfig:"GITHUB_CLIENT_SECRET"`
	Environment        string `envconfig:"ENVIRONMENT" default:"development"`
	AccessTokenTTL     int    `envconfig:"ACCESS_TOKEN_TTL" default:"3600"`
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

	if c.GitHubClientID != "" {
		fmtr("  GitHub OAuth: ✓ Enabled\n")
		fmtr("    Client ID: %s\n", MaskSecret(c.GitHubClientID))
		fmtr("    Client Secret: %s\n", MaskSecret(c.GitHubClientSecret))
	} else {
		fmtr("  GitHub OAuth: ✗ Disabled\n")
	}
}
