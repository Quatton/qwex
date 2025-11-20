package qsdk

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadConfig_ProjectConfig(t *testing.T) {
	// Create temp directory
	tempDir := t.TempDir()
	oldWd, _ := os.Getwd()
	os.Chdir(tempDir)
	defer os.Chdir(oldWd)

	// Create qwex.yaml in project root
	projectConfig := `
baseUrl: http://example.com:3000
apiVersion: v2
`
	os.WriteFile("qwex.yaml", []byte(projectConfig), 0644)

	// Load config
	cfg, err := LoadConfig("")
	if err != nil {
		t.Fatalf("LoadConfig failed: %v", err)
	}

	if cfg.BaseURL != "http://example.com:3000" {
		t.Errorf("Expected baseUrl http://example.com:3000, got %s", cfg.BaseURL)
	}

	if cfg.APIVersion != "v2" {
		t.Errorf("Expected apiVersion v2, got %s", cfg.APIVersion)
	}
}

func TestLoadConfig_LocalOverride(t *testing.T) {
	tempDir := t.TempDir()
	oldWd, _ := os.Getwd()
	os.Chdir(tempDir)
	defer os.Chdir(oldWd)

	// Create project config
	projectConfig := `
baseUrl: http://example.com:3000
apiVersion: v1
`
	os.WriteFile("qwex.yaml", []byte(projectConfig), 0644)

	// Create local override
	os.MkdirAll(ConfigRoot, 0755)
	localConfig := `
baseUrl: http://localhost:8080
apiVersion: v2
`
	os.WriteFile(filepath.Join(ConfigRoot, "config.yaml"), []byte(localConfig), 0644)

	// Load config
	cfg, err := LoadConfig("")
	if err != nil {
		t.Fatalf("LoadConfig failed: %v", err)
	}

	// Local override should win
	if cfg.BaseURL != "http://localhost:8080" {
		t.Errorf("Expected baseUrl http://localhost:8080 (from local override), got %s", cfg.BaseURL)
	}

	if cfg.APIVersion != "v2" {
		t.Errorf("Expected apiVersion v2 (from local override), got %s", cfg.APIVersion)
	}
}

func TestLoadConfig_Defaults(t *testing.T) {
	tempDir := t.TempDir()
	oldWd, _ := os.Getwd()
	os.Chdir(tempDir)
	defer os.Chdir(oldWd)

	// No config files - should use defaults
	cfg, err := LoadConfig("")
	if err != nil {
		t.Fatalf("LoadConfig failed: %v", err)
	}

	// Check defaults
	if cfg.BaseURL != "http://localhost:3000" {
		t.Errorf("Expected default baseUrl http://localhost:3000, got %s", cfg.BaseURL)
	}

	if cfg.APIVersion != "v1" {
		t.Errorf("Expected default apiVersion v1, got %s", cfg.APIVersion)
	}
}

func TestLoadConfig_ExplicitFile(t *testing.T) {
	tempDir := t.TempDir()
	oldWd, _ := os.Getwd()
	os.Chdir(tempDir)
	defer os.Chdir(oldWd)

	// Create custom config file
	customConfig := `
baseUrl: http://custom.com:9000
apiVersion: v3
`
	customPath := filepath.Join(tempDir, "custom-config.yaml")
	os.WriteFile(customPath, []byte(customConfig), 0644)

	// Load with explicit file
	cfg, err := LoadConfig(customPath)
	if err != nil {
		t.Fatalf("LoadConfig failed: %v", err)
	}

	if cfg.BaseURL != "http://custom.com:9000" {
		t.Errorf("Expected baseUrl http://custom.com:9000, got %s", cfg.BaseURL)
	}

	if cfg.APIVersion != "v3" {
		t.Errorf("Expected apiVersion v3, got %s", cfg.APIVersion)
	}
}
