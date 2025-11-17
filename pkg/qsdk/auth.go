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
)

type AuthClient struct {
	HttpClient     *client.Client
	CallbackServer *CallbackServer

	tokenCh chan string
	errCh   chan error
}

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

func NewAuthClient(
	client *client.Client,
) *AuthClient {
	return &AuthClient{
		HttpClient: client,
		tokenCh:    make(chan string, 1),
		errCh:      make(chan error, 1),
	}
}

func (ac *AuthClient) InitiateLoginWithGithub() (string, error) {
	callbackServer := &CallbackServer{}
	callbackURL, err := callbackServer.Start(ac.tokenCh, ac.errCh)
	if err != nil {
		return "", fmt.Errorf("failed to start callback server: %w", err)
	}
	ac.CallbackServer = callbackServer

	uBase, err := url.Parse(ac.HttpClient.Server)
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
