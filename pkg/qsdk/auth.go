package qsdk

import (
	"fmt"
	"net"
	"net/http"

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
	mux.HandleFunc("/callback", func(w http.ResponseWriter, r *http.Request) {
		// q := r.URL.Query()
		// if errStr := q.Get("error"); errStr != "" {
		// 	ch <- callbackResult{Err: fmt.Errorf("oauth error: %s", errStr)}
		// 	w.WriteHeader(http.StatusOK)
		// 	fmt.Fprintln(w, "Authentication failed. You may close this window.")
		// 	return
		// }
		// code := q.Get("code")
		// state := q.Get("state")
		// if code == "" {
		// 	ch <- callbackResult{Err: fmt.Errorf("missing code")}
		// 	w.WriteHeader(http.StatusBadRequest)
		// 	fmt.Fprintln(w, "Missing code. You may close this window.")
		// 	return
		// }
		// ch <- callbackResult{Code: code, State: state}
		// w.WriteHeader(http.StatusOK)

		w.WriteHeader(http.StatusOK)
		w.Write([]byte("Authentication successful. You can close this window.\n"))

		fmt.Printf("Callback received: %s %s\n", r.Method, r.URL.String())
		fmt.Println("Request headers:")
		for k, v := range r.Header {
			fmt.Printf("%s: %v\n", k, v)
		}

		fmt.Fprintln(w, "Authentication successful. You can close this window.")
	})

	srv := &http.Server{
		Addr:    addr,
		Handler: mux,
	}

	go func() {
		err := srv.ListenAndServe()
		ech <- err
	}()

	callbackURL := fmt.Sprintf("http://localhost:%d/callback", port)

	return callbackURL, nil
}

func NewAuthClient(
	client *client.Client,
) *AuthClient {
	return &AuthClient{
		HttpClient: client,
		tokenCh:    make(chan string),
		errCh:      make(chan error),
	}
}

func (ac *AuthClient) InitiateLoginWithGithub() (string, error) {
	callbackServer := &CallbackServer{}
	callbackURL, err := callbackServer.Start(ac.tokenCh, ac.errCh)
	if err != nil {
		return "", fmt.Errorf("failed to start callback server: %w", err)
	}
	ac.CallbackServer = callbackServer

	loginURL := fmt.Sprintf("%s/auth/github/login?from=%s", ac.HttpClient.Server, callbackURL)

	return loginURL, nil
}

func (ac *AuthClient) CompleteLoginInteractive() (string, error) {
	tokenCh := make(chan string)
	errCh := make(chan error)

	select {
	case res := <-tokenCh:
		return res, nil
	case err := <-errCh:
		return "", fmt.Errorf("login failed: %w", err)
	}
}
