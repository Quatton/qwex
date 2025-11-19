package qapi

import (
	"github.com/danielgtaylor/huma/v2"
	"github.com/danielgtaylor/huma/v2/adapters/humachi"
	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
)

type Api struct {
	Api    huma.API
	Router *chi.Mux
}

func NewApi() *Api {
	router := chi.NewMux()
	router.Use(middleware.Logger)
	router.Use(middleware.Recoverer)

	config := huma.DefaultConfig("qwex Controller", "1.0.0")

	config.Components.SecuritySchemes = map[string]*huma.SecurityScheme{
		"bearer": {
			Type:         "http",
			Scheme:       "bearer",
			BearerFormat: "JWT",
			Description:  "JWT token from /api/auth/callback",
		},
	}

	api := humachi.New(router, config)

	return &Api{Api: api, Router: router}
}
