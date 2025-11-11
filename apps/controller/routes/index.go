package routes

import (
	"context"
	"net/http"

	"github.com/danielgtaylor/huma/v2"
)

type RootOutput struct {
	Body struct {
		Message string `json:"message" example:"hello world from qwex controller" doc:"Welcome message"`
	}
}

func RegisterIndex(api huma.API) {
	huma.Register(api, huma.Operation{
		OperationID: "get-root",
		Method:      http.MethodGet,
		Path:        "/",
		Summary:     "Root endpoint",
		Description: "Returns a welcome message",
		Tags:        []string{"General"},
	}, func(ctx context.Context, input *struct{}) (*RootOutput, error) {
		resp := &RootOutput{}
		resp.Body.Message = "hello world from qwex controller"
		return resp, nil
	})
}
