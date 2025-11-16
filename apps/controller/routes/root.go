package routes

import (
	"github.com/danielgtaylor/huma/v2"
	"github.com/quatton/qwex/apps/controller/services"
)

func RegisterRoutes(api huma.API, svcs *services.Container) {
	RegisterIndex(api)
	RegisterHealth(api)
	RegisterMachines(api, svcs.Machines)
	RegisterIAM(api, svcs.IAM)
}
