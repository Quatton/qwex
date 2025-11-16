package authconfig

import (
	"log"
	"net/url"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-pkgz/auth"
	"github.com/go-pkgz/auth/avatar"
	"github.com/go-pkgz/auth/logger"
	"github.com/go-pkgz/auth/token"
	"github.com/quatton/qwex/apps/controller/config"
	"github.com/quatton/qwex/apps/controller/utils"
)

func NewAuthConfigService(cfg *config.EnvConfig) *auth.Service {
	options := auth.Opts{
		SecretReader: token.SecretFunc(func(id string) (string, error) {
			return cfg.AuthSecret, nil
		}),
		TokenDuration:  time.Hour * 24,
		CookieDuration: time.Hour * 24 * 30,
		Issuer:         "qwex",
		URL:            cfg.BaseURL,
		AvatarStore:    avatar.NewNoOp(),
		Validator: token.ValidatorFunc(func(_ string, claims token.Claims) bool {
			return true
		}),
		SecureCookies: utils.IsProd(),
		DisableXSRF:   !utils.IsProd(),
		Logger:        logger.Std,
	}

	service := auth.NewService(options)

	if cfg.GitHubClientID != "" && cfg.GitHubClientSecret != "" {
		service.AddProvider("github", cfg.GitHubClientID, cfg.GitHubClientSecret)
		log.Println("✓ GitHub OAuth provider configured")
		log.Printf("  GitHub login: %s/auth/github/login\n", cfg.BaseURL)
	} else {
		log.Println("ℹ GitHub OAuth not configured. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET to enable.")
	}

	if utils.IsDev() {
		if url, err := url.ParseRequestURI(cfg.BaseURL); err == nil {
			host := url.Hostname()
			if port, err := strconv.Atoi(url.Port()); err == nil {
				service.AddDevProvider(host, port)
				log.Println("✓ Dev auth provider configured")
				log.Printf("  Dev login: %s/auth/dev/login\n", cfg.BaseURL)
			} else {
				log.Fatalf("❌ Invalid BASE_URL port: %v\n", err)
			}
		} else {
			log.Fatalf("❌ Invalid BASE_URL: %v\n", err)
		}
	}

	return service
}

func MountAuthHandlers(auth *auth.Service, router chi.Router) {
	authHandler, avatarHandler := auth.Handlers()
	router.Mount("/auth", authHandler)
	router.Mount("/avatar", avatarHandler)
}
