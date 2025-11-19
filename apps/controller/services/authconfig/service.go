package authconfig

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/quatton/qwex/apps/controller/config"
	"github.com/quatton/qwex/apps/controller/schemas"
	"github.com/quatton/qwex/pkg/db/models"
	"github.com/quatton/qwex/pkg/qsdk"
	"github.com/uptrace/bun"
	"golang.org/x/oauth2"
	"golang.org/x/oauth2/github"
)

// AuthService encapsulates OAuth provider configuration and methods for
// generating and validating the small JWTs used by the system (state tokens
// and access tokens). It intentionally keeps provider details internal so
// callers work with simple method calls.
type AuthService struct {
	cfg          *config.EnvConfig
	githubConfig *oauth2.Config
	jwtSecret    []byte
	db           *bun.DB
	refreshTTL   time.Duration
}

// StateClaims is the short-lived JWT shape used for OAuth state parameter.
// It carries the original redirect URI and a small flag indicating whether
// the server should include the minted application token in the final
// redirect to the client. The RegisteredClaims control expiration/issuedAt.
type StateClaims struct {
	Provider     string `json:"provider"`
	RedirectURI  string `json:"redirect_uri"`
	IncludeToken bool   `json:"include_token"`
	jwt.RegisteredClaims
}

// GitHubUser represents the subset of fields we care about from GitHub's
// /user API. We map the provider identity into our internal user model when
// issuing application tokens.
type GitHubUser struct {
	ID        int64  `json:"id"`
	Login     string `json:"login"`
	Name      string `json:"name"`
	Email     string `json:"email"`
	AvatarURL string `json:"avatar_url"`
}

// NewAuthService constructs a new AuthService from an EnvConfig. If GitHub
// client credentials are present the service will be able to perform the
// OAuth code flow; otherwise methods that require provider access will
// return errors.
func NewAuthService(cfg *config.EnvConfig, dbClient *bun.DB) *AuthService {
	svc := &AuthService{
		cfg:        cfg,
		jwtSecret:  []byte(cfg.AuthSecret),
		db:         dbClient,
		refreshTTL: time.Duration(cfg.RefreshTokenTTL) * time.Second,
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

func (s *AuthService) AccessTokenTTL() int {
	return s.cfg.AccessTokenTTL
}

var ErrInvalidRefreshToken = errors.New("invalid refresh token")

// GenerateState builds a signed, short-lived JWT to be used as the OAuth
// `state` parameter. The returned token encodes where the user should be
// redirected after auth and whether the server should include the issued
// application token in that redirect. TTL is derived from the service's
// AccessTokenTTL configuration.
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

// ValidateState verifies the HMAC signature and expiry of a state token and
// returns the decoded StateClaims. It enforces HMAC signing method to avoid
// algorithm confusion attacks.
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

// GetAuthorizeURL returns the provider-specific authorize URL for a signed
// state. Returns the empty string if the provider is not configured.
func (s *AuthService) GetAuthorizeURL(state string) string {
	if s.githubConfig == nil {
		return ""
	}
	return s.githubConfig.AuthCodeURL(state)
}

// ExchangeCode exchanges a provider authorization code for an oauth2.Token.
// Returns an error if the provider is not configured.
func (s *AuthService) ExchangeCode(ctx context.Context, code string) (*oauth2.Token, error) {
	if s.githubConfig == nil {
		return nil, fmt.Errorf("github oauth not configured")
	}
	return s.githubConfig.Exchange(ctx, code)
}

// GetGitHubUser fetches the GitHub user profile for the provided oauth2
// access token. The method expects a successful 200 response and decodes a
// minimal set of fields into GitHubUser.
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

// IssueToken mints an application JWT for a local user and embeds the
// upstream provider identity (`github_id` / `github_login`) separately. The
// separation ensures a user's local login can change without losing the
// provider binding.
//
// The caller must supply the githubID/githubLogin values discovered during
// the OAuth flow; they are stored as top-level claims for simplicity.
func (s *AuthService) IssueToken(user *schemas.User, githubID, githubLogin string) (string, error) {
	uc := &qsdk.UserClaims{
		ID:          user.ID,
		Login:       user.Login,
		Name:        user.Name,
		Email:       user.Email,
		GithubID:    githubID,
		GithubLogin: githubLogin,
		Iss:         "qwex",
		Iat:         time.Now().Unix(),
		Exp:         time.Now().Add(time.Duration(s.cfg.AccessTokenTTL) * time.Second).Unix(),
	}

	claims := qsdk.ToClaims(uc)

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString(s.jwtSecret)
}

func (s *AuthService) SyncGitHubUser(ctx context.Context, ghUser *GitHubUser) (*models.User, error) {
	return s.findOrCreateUser(ctx, ghUser)
}

func (s *AuthService) IssueTokensWithRefresh(ctx context.Context, user *schemas.User, githubID, githubLogin string) (accessToken string, refreshToken string, err error) {
	token, err := s.IssueToken(user, githubID, githubLogin)
	if err != nil {
		return "", "", err
	}
	refreshToken, err = s.createRefreshToken(ctx, user.ID)
	if err != nil {
		return "", "", err
	}
	return token, refreshToken, nil
}

func (s *AuthService) RefreshTokens(ctx context.Context, refreshToken string) (string, string, error) {
	stored, err := s.verifyRefreshToken(ctx, refreshToken)
	if err != nil {
		return "", "", err
	}

	if err := s.deleteRefreshToken(ctx, stored.ID); err != nil {
		return "", "", err
	}

	user := stored.User
	if user == nil {
		if err := s.db.NewSelect().Model(stored).Relation("User").WherePK().Scan(ctx); err != nil {
			return "", "", err
		}
		user = stored.User
	}

	schemaUser := &schemas.User{
		ID:    user.ID.String(),
		Login: user.Login,
		Name:  user.Name,
		Email: user.Email,
	}

	return s.IssueTokensWithRefresh(ctx, schemaUser, user.ProviderID, user.Login)
}

func (s *AuthService) findOrCreateUser(ctx context.Context, ghUser *GitHubUser) (*models.User, error) {
	var user models.User
	err := s.db.NewSelect().
		Model(&user).
		Where("provider = ?", "github").
		Where("provider_id = ?", fmt.Sprintf("%d", ghUser.ID)).
		Scan(ctx)
	if err == nil {
		return &user, nil
	}
	if !errors.Is(err, sql.ErrNoRows) {
		return nil, err
	}

	user = models.User{
		Email:      ghUser.Email,
		Login:      ghUser.Login,
		Name:       ghUser.Name,
		Provider:   "github",
		ProviderID: fmt.Sprintf("%d", ghUser.ID),
	}

	_, err = s.db.NewInsert().Model(&user).Returning("*").Exec(ctx)
	if err != nil {
		return nil, err
	}
	return &user, nil
}

func (s *AuthService) createRefreshToken(ctx context.Context, userID string) (string, error) {
	buf := make([]byte, 32)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	raw := base64.RawURLEncoding.EncodeToString(buf)
	return raw, s.storeRefreshToken(ctx, userID, raw)
}

func (s *AuthService) storeRefreshToken(ctx context.Context, userID, token string) error {
	hash := hashToken(token)
	expires := time.Now().Add(s.refreshTTL)
	model := models.RefreshToken{TokenHash: hash, ExpiresAt: expires}
	uid, err := uuid.Parse(userID)
	if err != nil {
		return err
	}
	model.UserID = uid

	_, err = s.db.NewInsert().Model(&model).Exec(ctx)
	return err
}

func (s *AuthService) deleteRefreshToken(ctx context.Context, id uuid.UUID) error {
	_, err := s.db.NewDelete().
		Model((*models.RefreshToken)(nil)).
		Where("id = ?", id).
		Exec(ctx)
	return err
}

func (s *AuthService) verifyRefreshToken(ctx context.Context, token string) (*models.RefreshToken, error) {
	hash := hashToken(token)
	var stored models.RefreshToken
	err := s.db.NewSelect().
		Model(&stored).
		Where("token_hash = ?", hash).
		Where("expires_at > ?", time.Now()).
		Relation("User").
		Scan(ctx)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, ErrInvalidRefreshToken
		}
		return nil, err
	}
	return &stored, nil
}

func hashToken(token string) string {
	sum := sha256.Sum256([]byte(token))
	return hex.EncodeToString(sum[:])
}

// ValidateToken verifies an application JWT and returns a minimal `schemas.User`.
// This is a convenience for internal services that only need the user's id/login
// and email/name. It enforces HMAC signing and will error on tampering or expiry.
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
		// Map verified claims into UserClaims using shared helper to keep
		// mapping logic consistent with the CLI/SDK.
		uc, err := qsdk.FromMapClaims(claims)
		if err != nil {
			return nil, err
		}

		user := &schemas.User{
			ID:    uc.ID,
			Login: uc.Login,
			Name:  uc.Name,
			Email: uc.Email,
		}
		return user, nil
	}

	return nil, fmt.Errorf("invalid token")
}
