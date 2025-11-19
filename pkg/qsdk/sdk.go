package qsdk

import (
	"context"
	"fmt"
	"net/http"
	"time"

	"github.com/quatton/qwex/pkg/client"
	"github.com/quatton/qwex/pkg/qsdk/qerr"
	"github.com/spf13/viper"
)

// Sdk is a small wrapper around the generated API client with auth baked in.
// It provides a minimal surface that CLI commands can use so they don't need
// to wire keyring + client + headers themselves.
type Sdk struct {
	Client       *client.ClientWithResponses
	BaseURL      string
	Token        string
	RefreshToken string
}

// skipAuthEditorKey skips authRequestEditor when present in the context so the
// refresh call can execute without recursive token checks.
type skipAuthEditorKey struct{}

// ClearCredentials removes cached tokens for the SDK's base URL from the keyring
// and resets the in-memory copies.
func (s *Sdk) ClearCredentials() {
	if s == nil || s.BaseURL == "" {
		return
	}
	_ = DeleteToken(s.BaseURL)
	_ = DeleteRefreshToken(s.BaseURL)
	s.Token = ""
	s.RefreshToken = ""
}

// HandleUnauthorized inspects an HTTP status code and clears any cached token
// if it represents an authentication failure. It returns true when the status
// was 401 so callers can provide a helpful message to the user.
func (s *Sdk) HandleUnauthorized(status int) bool {
	if status != http.StatusUnauthorized {
		return false
	}
	s.ClearCredentials()
	return true
}

// NewSdk returns an initialized SDK instance with automatic token refresh.
func NewSdk() (*Sdk, error) {
	baseURL := viper.GetString(BaseUrlKey)
	access, refresh := LoadTokens(baseURL)

	sdk := &Sdk{
		BaseURL:      baseURL,
		Token:        access,
		RefreshToken: refresh,
	}

	c, err := client.NewClientWithResponses(baseURL, client.WithRequestEditorFn(sdk.authRequestEditor))
	if err != nil {
		return nil, err
	}
	sdk.Client = c
	return sdk, nil
}

func (s *Sdk) authRequestEditor(ctx context.Context, req *http.Request) error {
	if ctx.Value(skipAuthEditorKey{}) != nil {
		return nil
	}
	if err := s.ensureValidToken(ctx); err != nil {
		return err
	}
	if s.Token != "" {
		req.Header.Set("Authorization", "Bearer "+s.Token)
	}
	return nil
}

func (s *Sdk) ensureValidToken(ctx context.Context) error {
	if s.Token == "" {
		if s.RefreshToken == "" {
			return qerr.New(qerr.CodeUnauthorized, fmt.Errorf("missing credentials"))
		}
		return s.refreshTokens(ctx)
	}
	expired, err := IsTokenExpired(s.Token, 30*time.Second)
	if err != nil {
		return qerr.New(qerr.CodeUnknown, err)
	}
	if expired {
		return s.refreshTokens(ctx)
	}
	return nil
}

func (s *Sdk) refreshTokens(ctx context.Context) error {
	if s.RefreshToken == "" {
		return qerr.New(qerr.CodeUnauthorized, fmt.Errorf("missing refresh token"))
	}
	body := client.AuthRefreshJSONRequestBody{RefreshToken: s.RefreshToken}
	ctx = context.WithValue(ctx, skipAuthEditorKey{}, true)
	resp, err := s.Client.AuthRefreshWithResponse(ctx, body)
	if err != nil {
		return qerr.New(qerr.CodeRefreshFailed, err)
	}
	if resp.JSON200 == nil {
		status := 0
		if resp.HTTPResponse != nil {
			status = resp.StatusCode()
		}
		return qerr.New(qerr.CodeRefreshFailed, fmt.Errorf("refresh failed: status %d", status))
	}
	s.Token = resp.JSON200.AccessToken
	s.RefreshToken = resp.JSON200.RefreshToken
	if err := SaveTokens(s.BaseURL, s.Token, s.RefreshToken); err != nil {
		return qerr.New(qerr.CodeUnknown, err)
	}
	return nil
}
