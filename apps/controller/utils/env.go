package utils

import (
	"os"
	"strings"
)

// IsProd returns true if the application is running in production environment
func IsProd() bool {
	env := strings.ToLower(os.Getenv("ENVIRONMENT"))
	return env == "production" || env == "prod"
}

// IsDev returns true if the application is running in development environment
func IsDev() bool {
	env := strings.ToLower(os.Getenv("ENVIRONMENT"))
	return env == "development" || env == "dev" || env == ""
}

// GetEnvironment returns the current environment name
func GetEnvironment() string {
	env := os.Getenv("ENVIRONMENT")
	if env == "" {
		return "development"
	}
	return env
}
