package routes

import "github.com/danielgtaylor/huma/v2"

func RegisterRoutes(api huma.API) {
	RegisterIndex(api)
	RegisterHealth(api)
}
