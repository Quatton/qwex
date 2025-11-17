package routes

import (
	"context"
	"fmt"
	"log"
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

		// Create our user representation
		user := &schemas.User{
			ID:    fmt.Sprintf("%d", githubUser.ID),
			Login: githubUser.Login,
			Name:  githubUser.Name,
			Email: githubUser.Email,
		}

		token, err := svc.IssueToken(user, fmt.Sprintf("%d", githubUser.ID), githubUser.Login)
		if err != nil {
			return nil, huma.Error500InternalServerError(fmt.Sprintf("failed to issue token: %v", err))
		}

		// Always redirect. Whether we include the token is encoded in the state claims.
		rewritten, err := buildRedirectForCallback(claims.RedirectURI, token, claims.IncludeToken)
		if err != nil {
			return nil, huma.Error400BadRequest(fmt.Sprintf("invalid redirect_uri: %v", err))
		}

		log.Printf("redirecting to: %s", rewritten)

		return &CallbackOutput{
			Status:   http.StatusFound,
			Location: rewritten,
		}, nil
	})
}
func buildRedirectForCallback(rawURI, token string, includeToken bool) (string, error) {
	parsed, err := url.Parse(rawURI)
	if err != nil {
		return "", err
	}
	query := parsed.Query()
	if includeToken {
		query.Set("token", token)
	}
	parsed.RawQuery = query.Encode()
	return parsed.String(), nil
}
