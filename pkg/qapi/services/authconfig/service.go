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
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/quatton/qwex/pkg/db/models"
	"github.com/quatton/qwex/pkg/kv"
	"github.com/quatton/qwex/pkg/qapi/config"
	"github.com/quatton/qwex/pkg/qapi/schemas"
	"github.com/quatton/qwex/pkg/qauth"
	"github.com/quatton/qwex/pkg/qlog"
	"github.com/uptrace/bun"
	"golang.org/x/oauth2"
	"golang.org/x/oauth2/github"
)

const (
	// TokenAudience is the expected audience claim for access tokens.
	TokenAudience = "qwex"

	// Key prefixes for KV store
	kvPrefixState   = "auth:state:"
	kvPrefixRefresh = "auth:refresh:"
)

// AuthService encapsulates OAuth provider configuration and methods for
// generating and validating the small JWTs used by the system (state tokens
// and access tokens). It intentionally keeps provider details internal so
// callers work with simple method calls.
type AuthService struct {
	cfg              *config.EnvConfig
	githubConfig     *oauth2.Config
	jwtSecret        []byte
	db               *bun.DB
	kv               kv.Store
	refreshTTL       time.Duration
	allowedRedirects []string
}

func (s *AuthService) DB() *bun.DB {
	return s.db
}

// StateClaims is the short-lived JWT shape used for OAuth state parameter.
// It carries the original redirect URI and a small flag indicating whether
// the server should include the minted application token in the final
// redirect to the client. The RegisteredClaims control expiration/issuedAt.
type StateClaims struct {
	Provider     string `json:"provider"`
	RedirectURI  string `json:"redirect_uri"`
	IncludeToken bool   `json:"include_token"`
	StateID      string `json:"state_id"`
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
func NewAuthService(cfg *config.EnvConfig, dbClient *bun.DB, kvStore kv.Store) *AuthService {
	svc := &AuthService{
		cfg:        cfg,
		jwtSecret:  []byte(cfg.AuthSecret),
		db:         dbClient,
		kv:         kvStore,
		refreshTTL: time.Duration(cfg.RefreshTokenTTL) * time.Second,
	}

	if cfg.AllowedRedirects != "" {
		svc.allowedRedirects = strings.Split(cfg.AllowedRedirects, ",")
		for i := range svc.allowedRedirects {
			svc.allowedRedirects[i] = strings.TrimSpace(svc.allowedRedirects[i])
		}
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
		logger := qlog.NewDefault()
		logger.Info("github oauth not configured", "hint", "set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET to enable")
	}

	return svc
}

func (s *AuthService) AccessTokenTTL() int {
	return s.cfg.AccessTokenTTL
}

var ErrInvalidRefreshToken = errors.New("invalid refresh token")
var ErrStateAlreadyUsed = errors.New("state token already used")
var ErrRedirectNotAllowed = errors.New("redirect URI not allowed")

// IsAllowedRedirect checks if the given URI is in the allowlist.
func (s *AuthService) IsAllowedRedirect(uri string) bool {
	if len(s.allowedRedirects) == 0 {
		return false
	}

	parsed, err := url.Parse(uri)
	if err != nil {
		return false
	}

	// Reconstruct the origin (scheme + host)
	origin := fmt.Sprintf("%s://%s", parsed.Scheme, parsed.Host)

	for _, allowed := range s.allowedRedirects {
		if strings.HasPrefix(origin, allowed) || strings.HasPrefix(uri, allowed) {
			return true
		}
	}
	return false
}

// GenerateState builds a signed, short-lived JWT to be used as the OAuth
// `state` parameter. The returned token encodes where the user should be
// redirected after auth and whether the server should include the issued
// application token in that redirect. TTL is derived from the service's
// AccessTokenTTL configuration.
//
// The state token is stored in KV for single-use validation.
func (s *AuthService) GenerateState(
	ctx context.Context,
	provider string,
	redirectURI string,
	includeToken bool) (string, error) {

	// Validate redirect URI against allowlist
	if !s.IsAllowedRedirect(redirectURI) {
		return "", ErrRedirectNotAllowed
	}

	// Generate a unique state ID
	stateID := generateRandomString(32)

	claims := StateClaims{
		Provider:     provider,
		RedirectURI:  redirectURI,
		IncludeToken: includeToken,
		StateID:      stateID,
		RegisteredClaims: jwt.RegisteredClaims{
			Issuer:   "qwex",
			IssuedAt: jwt.NewNumericDate(time.Now()),
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(
				time.Duration(s.cfg.AccessTokenTTL) * time.Second,
			)),
		},
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	signedToken, err := token.SignedString(s.jwtSecret)
	if err != nil {
		return "", err
	}

	// Store state ID in KV for single-use validation
	// Value is "1" (exists marker), TTL matches token expiry
	ttl := time.Duration(s.cfg.AccessTokenTTL) * time.Second
	if err := s.kv.Set(ctx, kvPrefixState+stateID, []byte("1"), ttl); err != nil {
		return "", fmt.Errorf("failed to store state: %w", err)
	}

	return signedToken, nil
}

// ValidateState verifies the HMAC signature and expiry of a state token and
// returns the decoded StateClaims. It enforces HMAC signing method to avoid
// algorithm confusion attacks.
//
// This method also validates single-use: the state is deleted from KV after
// successful validation. If the state was already used, returns an error.
func (s *AuthService) ValidateState(ctx context.Context, state string) (*StateClaims, error) {
	parsed, err := jwt.ParseWithClaims(state, &StateClaims{}, func(token *jwt.Token) (interface{}, error) {
		if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
		}
		return s.jwtSecret, nil
	})

	if err != nil {
		return nil, err
	}

	claims, ok := parsed.Claims.(*StateClaims)
	if !ok || !parsed.Valid {
		return nil, errors.New("invalid state token")
	}

	// Check single-use: state must exist in KV
	_, err = s.kv.Get(ctx, kvPrefixState+claims.StateID)
	if err != nil {
		if errors.Is(err, kv.ErrNotFound) {
			return nil, ErrStateAlreadyUsed
		}
		return nil, fmt.Errorf("failed to validate state: %w", err)
	}

	// Delete state to prevent reuse
	if err := s.kv.Delete(ctx, kvPrefixState+claims.StateID); err != nil {
		// Log but don't fail - the state was valid
		logger := qlog.NewDefault()
		logger.Warn("failed to delete state after use", "error", err)
	}

	return claims, nil
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
	uc := &qauth.UserClaims{
		ID:          user.ID,
		Login:       user.Login,
		Name:        user.Name,
		Email:       user.Email,
		GithubID:    githubID,
		GithubLogin: githubLogin,
		Iss:         "qwex",
		Aud:         TokenAudience,
		Iat:         time.Now().Unix(),
		Exp:         time.Now().Add(time.Duration(s.cfg.AccessTokenTTL) * time.Second).Unix(),
	}

	claims := qauth.ToClaims(uc)

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString(s.jwtSecret)
}

func (s *AuthService) SyncGitHubUser(ctx context.Context, ghUser *GitHubUser, token *oauth2.Token) (*models.User, error) {
	return s.findOrCreateUser(ctx, ghUser, token)
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
	// Verify the refresh token and get the user ID
	userID, err := s.verifyRefreshToken(ctx, refreshToken)
	if err != nil {
		return "", "", err
	}

	// Delete the old refresh token (token rotation)
	hash := hashToken(refreshToken)
	if err := s.deleteRefreshTokenByHash(ctx, hash); err != nil {
		// Log but don't fail - the token was valid
		logger := qlog.NewDefault()
		logger.Warn("failed to delete old refresh token", "error", err)
	}

	// Fetch the user from DB
	var user models.User
	err = s.db.NewSelect().
		Model(&user).
		Where("id = ?", userID).
		Scan(ctx)
	if err != nil {
		return "", "", fmt.Errorf("failed to fetch user: %w", err)
	}

	schemaUser := &schemas.User{
		ID:    user.ID.String(),
		Login: user.Login,
		Name:  user.Name,
		Email: user.Email,
	}

	return s.IssueTokensWithRefresh(ctx, schemaUser, user.ProviderID, user.Login)
}

func (s *AuthService) findOrCreateUser(ctx context.Context, ghUser *GitHubUser, token *oauth2.Token) (*models.User, error) {
	logger := qlog.NewDefault()

	// Fetch Installation ID using the App JWT
	installationID, err := s.getInstallationID(ctx, ghUser.Login)
	if err != nil {
		// Log error but don't fail login? Or fail?
		// For now, let's log and proceed with 0 if not found (user might not have installed app yet)
		logger.Warn("failed to get installation ID", "user", ghUser.Login, "error", err)
	}

	var user models.User
	err = s.db.NewSelect().
		Model(&user).
		Where("provider = ?", "github").
		Where("provider_id = ?", fmt.Sprintf("%d", ghUser.ID)).
		Scan(ctx)

	if err == nil {
		// User exists, update info
		user.Login = ghUser.Login
		user.Name = ghUser.Name
		user.Email = ghUser.Email
		user.UpdatedAt = time.Now()
		if installationID != 0 {
			user.GithubInstallationID = installationID
		}

		_, err = s.db.NewUpdate().Model(&user).WherePK().Exec(ctx)
		if err != nil {
			return nil, err
		}
		return &user, nil
	}

	if !errors.Is(err, sql.ErrNoRows) {
		return nil, err
	}

	// Create new user
	user = models.User{
		Email:                ghUser.Email,
		Login:                ghUser.Login,
		Name:                 ghUser.Name,
		Provider:             "github",
		ProviderID:           fmt.Sprintf("%d", ghUser.ID),
		GithubInstallationID: installationID,
	}

	_, err = s.db.NewInsert().Model(&user).Returning("*").Exec(ctx)
	if err != nil {
		return nil, err
	}
	return &user, nil
}

// getInstallationID fetches the installation ID for a specific user
func (s *AuthService) getInstallationID(ctx context.Context, username string) (int64, error) {
	if s.cfg.GitHubAppID == 0 || s.cfg.GitHubAppPrivateKey == "" {
		return 0, nil
	}

	jwtToken, err := s.generateAppJWT()
	if err != nil {
		return 0, err
	}

	req, err := http.NewRequestWithContext(ctx, "GET", fmt.Sprintf("https://api.github.com/users/%s/installation", username), nil)
	if err != nil {
		return 0, err
	}
	req.Header.Set("Authorization", "Bearer "+jwtToken)
	req.Header.Set("Accept", "application/vnd.github+json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return 0, nil // Not installed
	}

	if resp.StatusCode != http.StatusOK {
		return 0, fmt.Errorf("github api returned status %d", resp.StatusCode)
	}

	var installation struct {
		ID int64 `json:"id"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&installation); err != nil {
		return 0, err
	}

	return installation.ID, nil
}

// generateAppJWT creates a JWT for authenticating as the GitHub App
func (s *AuthService) generateAppJWT() (string, error) {
	claims := jwt.RegisteredClaims{
		Issuer:    fmt.Sprintf("%d", s.cfg.GitHubAppID),
		IssuedAt:  jwt.NewNumericDate(time.Now().Add(-60 * time.Second)),
		ExpiresAt: jwt.NewNumericDate(time.Now().Add(10 * time.Minute)),
	}

	token := jwt.NewWithClaims(jwt.SigningMethodRS256, claims)

	keyBlock, _ := base64.StdEncoding.DecodeString(s.cfg.GitHubAppPrivateKey)
	// If not base64, try plain PEM
	if len(keyBlock) == 0 {
		keyBlock = []byte(s.cfg.GitHubAppPrivateKey)
	}

	// We need to parse the private key.
	// Assuming standard PEM format.
	signKey, err := jwt.ParseRSAPrivateKeyFromPEM(keyBlock)
	if err != nil {
		// Try treating it as raw key if it's not PEM formatted (e.g. from env var without newlines)
		// But standard is PEM. Let's assume user provides valid PEM or we might need to fix newlines.
		return "", fmt.Errorf("failed to parse private key: %w", err)
	}

	return token.SignedString(signKey)
}

// GetInstallationToken generates a short-lived access token for the installation
func (s *AuthService) GetInstallationToken(ctx context.Context, installationID int64) (string, error) {
	if installationID == 0 {
		return "", errors.New("installation id is 0")
	}

	jwtToken, err := s.generateAppJWT()
	if err != nil {
		return "", err
	}

	url := fmt.Sprintf("https://api.github.com/app/installations/%d/access_tokens", installationID)
	req, err := http.NewRequestWithContext(ctx, "POST", url, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("Authorization", "Bearer "+jwtToken)
	req.Header.Set("Accept", "application/vnd.github+json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusCreated {
		return "", fmt.Errorf("github api returned status %d", resp.StatusCode)
	}

	var tokenResp struct {
		Token string `json:"token"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&tokenResp); err != nil {
		return "", err
	}

	return tokenResp.Token, nil
}

// generateRandomString generates a cryptographically secure random string
// of the specified length using base64url encoding.
func generateRandomString(length int) string {
	buf := make([]byte, length)
	if _, err := rand.Read(buf); err != nil {
		// This should never fail in practice
		panic(fmt.Sprintf("crypto/rand failed: %v", err))
	}
	return base64.RawURLEncoding.EncodeToString(buf)[:length]
}

func (s *AuthService) createRefreshToken(ctx context.Context, userID string) (string, error) {
	buf := make([]byte, 32)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	raw := base64.RawURLEncoding.EncodeToString(buf)
	return raw, s.storeRefreshToken(ctx, userID, raw)
}

// storeRefreshToken stores the refresh token in KV with the user ID as value.
// The token hash is used as the key for secure lookup.
func (s *AuthService) storeRefreshToken(ctx context.Context, userID, token string) error {
	hash := hashToken(token)
	key := kvPrefixRefresh + hash
	return s.kv.Set(ctx, key, []byte(userID), s.refreshTTL)
}

// deleteRefreshTokenByHash removes a refresh token from KV by its hash.
func (s *AuthService) deleteRefreshTokenByHash(ctx context.Context, tokenHash string) error {
	return s.kv.Delete(ctx, kvPrefixRefresh+tokenHash)
}

// verifyRefreshToken validates a refresh token and returns the associated user ID.
// Returns ErrInvalidRefreshToken if the token doesn't exist or has expired.
func (s *AuthService) verifyRefreshToken(ctx context.Context, token string) (string, error) {
	hash := hashToken(token)
	key := kvPrefixRefresh + hash

	data, err := s.kv.Get(ctx, key)
	if err != nil {
		if errors.Is(err, kv.ErrNotFound) {
			return "", ErrInvalidRefreshToken
		}
		return "", err
	}

	return string(data), nil
}

func hashToken(token string) string {
	sum := sha256.Sum256([]byte(token))
	return hex.EncodeToString(sum[:])
}

// ValidateToken verifies an application JWT and returns a minimal `schemas.User`.
// This is a convenience for internal services that only need the user's id/login
// and email/name. It enforces HMAC signing, validates the audience claim,
// and will error on tampering or expiry.
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
		uc, err := qauth.FromMapClaims(claims)
		if err != nil {
			return nil, err
		}

		// Validate audience claim
		if uc.Aud != TokenAudience {
			return nil, fmt.Errorf("invalid audience: expected %q, got %q", TokenAudience, uc.Aud)
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
