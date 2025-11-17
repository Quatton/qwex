package qsdk

import (
	"context"
	"net/http"

	"github.com/quatton/qwex/pkg/client"
	"github.com/spf13/viper"
)

type Sdk struct {
	Client  *client.ClientWithResponses
	BaseURL string
	Token   string
}

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
