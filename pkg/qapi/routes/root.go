package routes

import (
	"github.com/danielgtaylor/huma/v2"
	"github.com/quatton/qwex/pkg/qapi/services"
)

func RegisterAPI(api huma.API, svcs *services.Services) {
	if svcs == nil {
		RegisterIAM(api, nil)
		RegisterAuthConfig(api, nil)
		RegisterRuns(api, nil, nil)
	} else {
		RegisterIAM(api, svcs.IAM)
		RegisterAuthConfig(api, svcs.Auth)
		RegisterRuns(api, svcs.Runners, svcs.S3)
	}
}
