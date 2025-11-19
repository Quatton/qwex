package routes

import (
	"context"

	"github.com/danielgtaylor/huma/v2"
	"github.com/quatton/qwex/pkg/qapi/schemas"
	"github.com/quatton/qwex/pkg/qapi/services/iam"
)

func RegisterIAM(api huma.API, svc *iam.IAMService) {
	huma.Register(api, huma.Operation{
		OperationID: "get-me",
		Method:      "GET",
		Path:        "/api/me",
		Summary:     "Get current user",
		Description: "Retrieves information about the currently authenticated user",
		Tags: []string{
			TagIam.String(),
		},
		Security: BearerAuth,
	}, func(ctx context.Context, input *struct{}) (*schemas.MeResponse, error) {
		user, _ := svc.Get(ctx)
		if user == nil {
			return nil, huma.Error401Unauthorized(
				"Authentication required",
			)
		}
		resp := &schemas.MeResponse{}
		resp.Body.User.ID = user.ID
		resp.Body.User.Login = user.Login
		resp.Body.User.Name = user.Name
		resp.Body.User.Email = user.Email
		return resp, nil
	})
}
