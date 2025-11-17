package main

import (
	"fmt"
	"log"
	"net/http"
	"os"

	"github.com/danielgtaylor/huma/v2"
	"github.com/danielgtaylor/huma/v2/adapters/humachi"
	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/joho/godotenv"
	"github.com/quatton/qwex/apps/controller/config"
	"github.com/quatton/qwex/apps/controller/routes"
	"github.com/quatton/qwex/apps/controller/services"
	"github.com/quatton/qwex/apps/controller/services/authconfig"
	"github.com/quatton/qwex/apps/controller/services/iam"
	"github.com/quatton/qwex/apps/controller/services/machines"
	"github.com/quatton/qwex/apps/controller/utils"
)

func main() {
	if utils.IsDev() {
		if err := godotenv.Load(); err != nil {
			log.Println("ℹ No .env file found")
		} else {
			log.Println("✓ Loaded .env file")
		}
	}

	cfg, err := config.ValidateEnv()
	if err != nil {
		log.Fatalf("❌ %v\n", err)
	}

	cfg.Print(log.Printf)

	router := chi.NewMux()
	router.Use(middleware.Logger)
	router.Use(middleware.Recoverer)

	auth := authconfig.NewAuthService(cfg)

	iamSvc := iam.NewIAMService(auth)
	machinesSvc := machines.NewMachinesService(iamSvc)

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

	svcs := &services.Container{
		IAM:      iamSvc,
		Machines: machinesSvc,
	}

	api.UseMiddleware(iamSvc.Middleware())
	routes.RegisterRoutes(api, svcs)
	routes.RegisterAuthConfig(api, auth)

	port := cfg.Port
	addr := fmt.Sprintf(":%s", port)

	log.Printf("🚀 Controller starting on %s\n", addr)
	log.Printf("📚 OpenAPI docs: %s/docs\n", cfg.BaseURL)
	log.Printf("📄 OpenAPI spec: %s/openapi.json\n", cfg.BaseURL)
	log.Printf("🔐 Auth endpoints:\n")

	log.Printf("   - Authorize: %s/api/auth/login", cfg.BaseURL)

	if err := http.ListenAndServe(addr, router); err != nil {
		fmt.Fprintf(os.Stderr, "Server error: %v\n", err)
		os.Exit(1)
	}
}
