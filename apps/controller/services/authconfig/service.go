package authconfig

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/quatton/qwex/apps/controller/config"
	"github.com/quatton/qwex/apps/controller/schemas"
	"golang.org/x/oauth2"
	"golang.org/x/oauth2/github"
)

type AuthService struct {
	cfg          *config.EnvConfig
	githubConfig *oauth2.Config
	jwtSecret    []byte
}

type StateClaims struct {
	Provider     string `json:"provider"`
	RedirectURI  string `json:"redirect_uri"`
	IncludeToken bool   `json:"include_token"`
	jwt.RegisteredClaims
}

type GitHubUser struct {
	ID        int64  `json:"id"`
	Login     string `json:"login"`
	Name      string `json:"name"`
	Email     string `json:"email"`
	AvatarURL string `json:"avatar_url"`
}

func NewAuthService(cfg *config.EnvConfig) *AuthService {
	svc := &AuthService{
		cfg:       cfg,
		jwtSecret: []byte(cfg.AuthSecret),
	}

	if cfg.GitHubClientID != "" && cfg.GitHubClientSecret != "" {
		svc.githubConfig = &oauth2.Config{
			ClientID:     cfg.GitHubClientID,
			ClientSecret: cfg.GitHubClientSecret,
			Endpoint:     github.Endpoint,
			Scopes:       []string{"user:email"},
			RedirectURL:  fmt.Sprintf("%s/api/auth/callback", cfg.BaseURL),
		}
	} else {
		log.Println("ℹ GitHub OAuth not configured. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET to enable.")
	}

	return svc
}

func (s *AuthService) GenerateState(
	provider string,
	redirectURI string,
	includeToken bool) (string, error) {
	claims := StateClaims{
		Provider:     provider,
		RedirectURI:  redirectURI,
		IncludeToken: includeToken,
		RegisteredClaims: jwt.RegisteredClaims{
			Issuer:   "qwex",
			IssuedAt: jwt.NewNumericDate(time.Now()),
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(
				time.Duration(s.cfg.AccessTokenTTL) * time.Second,
			)),
		},
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString(s.jwtSecret)
}

func (s *AuthService) ValidateState(state string) (*StateClaims, error) {
	parsed, err := jwt.ParseWithClaims(state, &StateClaims{}, func(token *jwt.Token) (interface{}, error) {
		if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
		}
		return s.jwtSecret, nil
	})

	if err != nil {
		return nil, err
	}

	if claims, ok := parsed.Claims.(*StateClaims); ok && parsed.Valid {
		return claims, nil
	}

	return nil, errors.New("invalid state token")
}

func (s *AuthService) GetAuthorizeURL(state string) string {
	if s.githubConfig == nil {
		return ""
	}
	return s.githubConfig.AuthCodeURL(state)
}

func (s *AuthService) ExchangeCode(ctx context.Context, code string) (*oauth2.Token, error) {
	if s.githubConfig == nil {
		return nil, fmt.Errorf("github oauth not configured")
	}
	return s.githubConfig.Exchange(ctx, code)
}

func (s *AuthService) GetGitHubUser(ctx context.Context, token *oauth2.Token) (*GitHubUser, error) {
	client := s.githubConfig.Client(ctx, token)
	resp, err := client.Get("https://api.github.com/user")
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("github api returned status %d", resp.StatusCode)
	}

	var user GitHubUser
	if err := json.NewDecoder(resp.Body).Decode(&user); err != nil {
		return nil, err
	}

	return &user, nil
}

func (s *AuthService) IssueToken(user *schemas.User) (string, error) {
	claims := jwt.MapClaims{
		"sub":   user.ID,
		"login": user.Login,
		"name":  user.Name,
		"email": user.Email,
		"iss":   "qwex",
		"iat":   time.Now().Unix(),
		"exp":   time.Now().Add(24 * time.Hour).Unix(),
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString(s.jwtSecret)
}

func (s *AuthService) ValidateToken(tokenString string) (*schemas.User, error) {
	token, err := jwt.Parse(tokenString, func(token *jwt.Token) (interface{}, error) {
		if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
		}
		return s.jwtSecret, nil
	})

	if err != nil {
		return nil, err
	}

	if claims, ok := token.Claims.(jwt.MapClaims); ok && token.Valid {
		user := &schemas.User{
			Login: claims["login"].(string),
			Name:  claims["name"].(string),
			Email: claims["email"].(string),
		}
		// Parse ID from "sub" claim
		if sub, ok := claims["sub"].(string); ok {
			user.ID = sub
		}
		return user, nil
	}

	return nil, fmt.Errorf("invalid token")
}
