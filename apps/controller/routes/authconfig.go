package routes

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/url"

	"github.com/danielgtaylor/huma/v2"
	"github.com/quatton/qwex/apps/controller/schemas"
	"github.com/quatton/qwex/apps/controller/services/authconfig"
)

type AuthorizeInput struct {
	RedirectURI  string `query:"redirect_uri" doc:"URI to redirect after authentication" example:"http://localhost:8080/callback"`
	Provider     string `query:"provider" enum:"github" doc:"Upstream OAuth provider" example:"github" default:"github"`
	IncludeToken bool   `query:"include_token" doc:"Whether to include the minted token in the callback redirect" default:"true"`
}

type AuthorizeOutput struct {
	Status   int            `json:"-" doc:"HTTP status code"`
	Location string         `header:"Location" doc:"Redirect location when response_mode=redirect"`
	Body     *AuthorizeBody `json:"body,omitempty"`
}

type AuthorizeBody struct {
	AuthorizeURL string `json:"authorize_url" doc:"URL to redirect user to for OAuth authorization"`
	State        string `json:"state" doc:"State parameter for CSRF protection"`
}

type CallbackInput struct {
	Code  string `query:"code" required:"true" doc:"Authorization code from OAuth provider"`
	State string `query:"state" required:"true" doc:"State parameter for CSRF validation"`
}

type CallbackOutput struct {
	Status   int    `json:"-" doc:"HTTP status code"`
	Location string `header:"Location" doc:"Redirect location when response_mode=redirect"`
}

func RegisterAuthConfig(api huma.API, svc *authconfig.AuthService) {
	huma.Register(api, huma.Operation{
		OperationID: "auth-login",
		Method:      "GET",
		Path:        "/api/auth/login",
		Summary:     "Initiate authentication",
		Description: "Starts the OAuth authentication process by redirecting to the provider",
		Tags:        []string{TagIam.String()},
	}, func(ctx context.Context, input *AuthorizeInput) (*AuthorizeOutput, error) {
		if input.Provider != "github" {
			return nil, huma.Error400BadRequest("only 'github' provider is currently supported")
		}

		if input.RedirectURI == "" {
			return nil, huma.Error400BadRequest("redirect_uri is required")
		}

		state, err := svc.GenerateState(input.Provider, input.RedirectURI, input.IncludeToken)
		if err != nil {
			return nil, huma.Error500InternalServerError(fmt.Sprintf("failed to generate state: %v", err))
		}
		authorizeURL := svc.GetAuthorizeURL(state)

		if authorizeURL == "" {
			return nil, huma.Error500InternalServerError("GitHub OAuth is not configured")
		}

		return &AuthorizeOutput{
			Status:   http.StatusFound,
			Location: authorizeURL,
		}, nil
	})

	// Callback endpoint - handles OAuth callback and issues token
	huma.Register(api, huma.Operation{
		OperationID: "auth-callback",
		Method:      "GET",
		Path:        "/api/auth/callback",
		Summary:     "OAuth callback handler",
		Description: "Handles the OAuth callback, exchanges code for token, and returns JWT",
		Tags:        []string{TagIam.String()},
	}, func(ctx context.Context, input *CallbackInput) (*CallbackOutput, error) {
		// Validate state
		claims, err := svc.ValidateState(input.State)
		if err != nil {
			return nil, huma.Error400BadRequest("invalid or expired state parameter")
		}

		// Exchange code for OAuth token

		oauthToken, err := svc.ExchangeCode(ctx, input.Code)
		if err != nil {
			return nil, huma.Error500InternalServerError(fmt.Sprintf("failed to exchange code: %v", err))
		}

		// Get user info from GitHub
		githubUser, err := svc.GetGitHubUser(ctx, oauthToken)
		if err != nil {
			return nil, huma.Error500InternalServerError(fmt.Sprintf("failed to get user info: %v", err))
		}

		// Persist or find user
		dbUser, err := svc.SyncGitHubUser(ctx, githubUser)
		if err != nil {
			return nil, huma.Error500InternalServerError(fmt.Sprintf("failed to sync user: %v", err))
		}

		user := &schemas.User{
			ID:    dbUser.ID.String(),
			Login: dbUser.Login,
			Name:  dbUser.Name,
			Email: dbUser.Email,
		}

		accessToken, refreshToken, err := svc.IssueTokensWithRefresh(ctx, user, dbUser.ProviderID, dbUser.Login)
		if err != nil {
			return nil, huma.Error500InternalServerError(fmt.Sprintf("failed to issue token: %v", err))
		}

		// Always redirect. Whether we include the token is encoded in the state claims.
		rewritten, err := buildRedirectForCallback(claims.RedirectURI, accessToken, refreshToken, claims.IncludeToken)
		if err != nil {
			return nil, huma.Error400BadRequest(fmt.Sprintf("invalid redirect_uri: %v", err))
		}

		return &CallbackOutput{
			Status:   http.StatusFound,
			Location: rewritten,
		}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "auth-refresh",
		Method:      "POST",
		Path:        "/api/auth/refresh",
		Summary:     "Refresh access token",
		Description: "Exchanges a valid refresh token for a new access token and rotated refresh token",
		Tags:        []string{TagIam.String()},
	}, func(ctx context.Context, input *schemas.RefreshTokenRequest) (*schemas.RefreshTokenResponse, error) {
		refreshToken := input.Body.RefreshToken
		if refreshToken == "" {
			return nil, huma.Error400BadRequest("refresh_token is required")
		}

		access, rotated, err := svc.RefreshTokens(ctx, refreshToken)
		if err != nil {
			if errors.Is(err, authconfig.ErrInvalidRefreshToken) {
				return nil, huma.Error401Unauthorized("invalid or expired refresh token")
			}
			return nil, huma.Error500InternalServerError(fmt.Sprintf("failed to refresh token: %v", err))
		}

		resp := &schemas.RefreshTokenResponse{}
		resp.Body.AccessToken = access
		resp.Body.RefreshToken = rotated
		resp.Body.TokenType = "bearer"
		resp.Body.ExpiresIn = svc.AccessTokenTTL()
		return resp, nil
	})
}
func buildRedirectForCallback(rawURI, token, refreshToken string, includeToken bool) (string, error) {
	parsed, err := url.Parse(rawURI)
	if err != nil {
		return "", err
	}
	query := parsed.Query()
	if includeToken {
		query.Set("token", token)
		if refreshToken != "" {
			query.Set("refresh_token", refreshToken)
		}
	}
	parsed.RawQuery = query.Encode()
	return parsed.String(), nil
}
