package qsdk

import (
	"context"
	"net/http"

	"github.com/quatton/qwex/pkg/client"
	"github.com/spf13/viper"
)

// Sdk is a small wrapper around the generated API client with auth baked in.
// It provides a minimal surface that CLI commands can use so they don't need
// to wire keyring + client + headers themselves.
type Sdk struct {
	Client  *client.ClientWithResponses
	BaseURL string
	Token   string
}

// ClearToken removes the cached token for the SDK's base URL from the keyring.
// It is safe to call even if no token has been saved yet.
func (s *Sdk) ClearToken() {
	if s == nil || s.BaseURL == "" {
		return
	}
	_ = DeleteToken(s.BaseURL)
}

// HandleUnauthorized inspects an HTTP status code and clears any cached token
// if it represents an authentication failure. It returns true when the status
// was 401 so callers can provide a helpful message to the user.
func (s *Sdk) HandleUnauthorized(status int) bool {
	if status != http.StatusUnauthorized {
		return false
	}
	s.ClearToken()
	return true
}

// NewSdk returns an initialized SDK instance. It reads the base URL from
// viper (qsdk.BaseUrlKey) and attempts to load a saved token from the OS
// keyring. If a token is present it will be injected into outgoing requests
// using the generated client's RequestEditorFn mechanism.
//
// Note: token injection uses the unverified token stored in the user's
// keyring. The SDK does not validate token expiry before injecting it; caller
// code should handle API errors and possibly re-authenticate.
func NewSdk() (*Sdk, error) {
	baseURL := viper.GetString(BaseUrlKey)

	token, _ := LoadToken(baseURL)

	c, err := client.NewClientWithResponses(baseURL, client.WithRequestEditorFn(func(ctx context.Context, req *http.Request) error {
		if token != "" {
			req.Header.Set("Authorization", "Bearer "+token)
		}
		return nil
	}))
	if err != nil {
		return nil, err
	}

	return &Sdk{Client: c, BaseURL: baseURL, Token: token}, nil
}
