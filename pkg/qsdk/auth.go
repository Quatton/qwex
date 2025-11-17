package qsdk

import (
	"context"
	"fmt"

	// keep logging import available for future debug; currently not used
	"net"
	"net/http"
	"net/url"
	"time"

	"github.com/quatton/qwex/pkg/client"
	"github.com/spf13/viper"
)

// AuthClient orchestrates an interactive browser-based OAuth login for CLI
// users. It starts a temporary loopback HTTP server to receive the provider
// redirect and delivers the resulting token over a buffered channel. The
// buffer prevents the HTTP handler from blocking if the caller is slow to
// receive.
type AuthClient struct {
	HttpClient     *client.Client
	CallbackServer *CallbackServer

	tokenCh chan string
	errCh   chan error
}

// CallbackServer hosts a temporary HTTP listener on localhost used during the
// interactive CLI login flow. It exposes the chosen listener address in
// `Addr` so callers can inspect or reuse it if needed.
type CallbackServer struct {
	Addr string
}

func getFreePort() (port int, err error) {
	var a *net.TCPAddr
	if a, err = net.ResolveTCPAddr("tcp", "localhost:0"); err == nil {
		var l *net.TCPListener
		if l, err = net.ListenTCP("tcp", a); err == nil {
			defer l.Close()
			return l.Addr().(*net.TCPAddr).Port, nil
		}
	}
	return 0, err
}

// Start launches a temporary localhost HTTP server and registers a single
// `/callback` handler. The server will attempt to gracefully shutdown after
// receiving the OAuth redirect. Tokens received on the querystring are sent
// to `ch` and any server-level error is sent to `ech`.
//
// Returns the callback URL that should be passed to the upstream OAuth
// authorize endpoint (e.g. "http://localhost:12345/callback").
func (cs *CallbackServer) Start(
	ch chan<- string,
	ech chan<- error,
) (string, error) {
	port, err := getFreePort()
	if err != nil {
		return "", fmt.Errorf("failed to get free port: %w", err)
	}

	addr := fmt.Sprintf(":%d", port)
	cs.Addr = addr

	mux := http.NewServeMux()
	var srv *http.Server
	mux.HandleFunc("/callback", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("Authentication successful. You can close this window.\n"))

		if f, ok := w.(http.Flusher); ok {
			f.Flush()
		}

		token := r.URL.Query().Get("token")
		if token == "" {
			ech <- fmt.Errorf("no token in callback")
			if srv != nil {
				go func() { _ = srv.Shutdown(context.Background()) }()
			}
			return
		}

		ch <- token

		if srv != nil {
			go func() { _ = srv.Shutdown(context.Background()) }()
		}
	})

	srv = &http.Server{
		Addr:    addr,
		Handler: mux,
	}

	go func() {
		err := srv.ListenAndServe()
		if err != nil && err != http.ErrServerClosed {
			ech <- err
		} else {
			ech <- nil
		}
	}()

	callbackURL := fmt.Sprintf("http://localhost:%d/callback", port)

	return callbackURL, nil
}

// NewAuthClient constructs an AuthClient. The provided http client is kept on
// the struct for future extensibility (e.g. to call the server to obtain the
// provider authorize URL). Currently the client parameter may be nil.
func NewAuthClient(
	client *client.Client,
) *AuthClient {
	return &AuthClient{
		HttpClient: client,
		tokenCh:    make(chan string, 1),
		errCh:      make(chan error, 1),
	}
}

// InitiateLoginWithGithub starts the temporary callback server and returns a
// fully-formed login URL suitable for opening in a browser. The returned URL
// includes the callback URL as the `redirect_uri` query param so the provider
// will redirect back to the local loopback server. Callers must then call
// CompleteLoginInteractive to receive the token or error.
func (ac *AuthClient) InitiateLoginWithGithub() (string, error) {
	callbackServer := &CallbackServer{}
	callbackURL, err := callbackServer.Start(ac.tokenCh, ac.errCh)
	if err != nil {
		return "", fmt.Errorf("failed to start callback server: %w", err)
	}
	ac.CallbackServer = callbackServer

	uBase, err := url.Parse(viper.GetString(BaseUrlKey))
	if err != nil {
		return "", fmt.Errorf("invalid server URL: %w", err)
	}
	rel, _ := url.Parse("/api/auth/login")
	u := uBase.ResolveReference(rel)
	q := u.Query()
	q.Set("redirect_uri", callbackURL)
	u.RawQuery = q.Encode()
	loginURL := u.String()

	return loginURL, nil
}

// CompleteLoginInteractive waits for the token that the callback server will
// write to the internal channel. It returns the token string on success.
//
// The method uses a 2 minute timeout to avoid leaving the CLI waiting
// indefinitely. This timeout is intentionally short for interactive UX but
// can be adjusted if needed.
func (ac *AuthClient) CompleteLoginInteractive() (string, error) {
	select {
	case res := <-ac.tokenCh:
		return res, nil
	case err := <-ac.errCh:
		return "", fmt.Errorf("login failed: %w", err)
	case <-time.After(2 * time.Minute):
		return "", fmt.Errorf("login timed out")
	}
}
