package main

import (
	"fmt"
	"net/http"
	"os"

	"github.com/danielgtaylor/huma/v2"
	"github.com/danielgtaylor/huma/v2/adapters/humachi"
	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/quatton/qwex/apps/controller/routes"
)

func main() {
	router := chi.NewMux()
	router.Use(middleware.Logger)
	router.Use(middleware.Recoverer)

	api := humachi.New(router, huma.DefaultConfig("qwex Controller", "1.0.0"))

	routes.RegisterRoutes(api)

	port := os.Getenv("PORT")
	if port == "" {
		port = "3000"
	}

	addr := fmt.Sprintf(":%s", port)
	fmt.Printf("Controller starting on %s\n", addr)
	fmt.Printf("OpenAPI docs available at http://localhost:%s/docs\n", port)
	fmt.Printf("OpenAPI spec available at http://localhost:%s/openapi.json\n", port)

	if err := http.ListenAndServe(addr, router); err != nil {
		fmt.Fprintf(os.Stderr, "Server error: %v\n", err)
		os.Exit(1)
	}
}
