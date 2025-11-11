package main

import (
	"context"
	"fmt"
	"net/http"
	"os"

	"github.com/danielgtaylor/huma/v2"
	"github.com/danielgtaylor/huma/v2/adapters/humachi"
	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
)

// RootOutput represents the root endpoint response
type RootOutput struct {
	Body struct {
		Message string `json:"message" example:"hello world from qwex controller" doc:"Welcome message"`
	}
}

// HealthOutput represents the health check response
type HealthOutput struct {
	Body struct {
		Status string `json:"status" example:"ok" doc:"Health status"`
	}
}

func main() {
	// Create Chi router with middleware
	router := chi.NewMux()
	router.Use(middleware.Logger)
	router.Use(middleware.Recoverer)

	// Create Huma API with OpenAPI config
	api := humachi.New(router, huma.DefaultConfig("qwex Controller", "1.0.0"))

	// Register root endpoint
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

	// Register health check endpoint
	huma.Register(api, huma.Operation{
		OperationID: "health-check",
		Method:      http.MethodGet,
		Path:        "/health",
		Summary:     "Health check",
		Description: "Returns the health status of the controller",
		Tags:        []string{"General"},
	}, func(ctx context.Context, input *struct{}) (*HealthOutput, error) {
		resp := &HealthOutput{}
		resp.Body.Status = "ok"
		return resp, nil
	})

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
