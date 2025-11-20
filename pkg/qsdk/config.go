package qsdk

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/spf13/viper"
)

type Config struct {
	BaseURL    string            `mapstructure:"baseUrl"`
	APIVersion string            `mapstructure:"apiVersion"`
	Env        map[string]string `mapstructure:"env"`
	WorkingDir string            `mapstructure:"working_dir"`

	v *viper.Viper // instance-specific viper
}

const (
	EnvPrefix  = "QWEX"
	ConfigName = "qwex"
	ConfigRoot = ".qwex"

	BaseUrlKey    = "baseUrl"
	ApiVersionKey = "apiVersion"
)

// LoadConfig creates a new Config instance with its own viper
// This is the only way to load config (no global state)
func LoadConfig(cfgFile string) (*Config, error) {
	v := viper.New()

	v.SetEnvPrefix(EnvPrefix)
	v.SetEnvKeyReplacer(strings.NewReplacer(".", "_", "-", "_"))
	v.AutomaticEnv()

	if cfgFile != "" {
		v.SetConfigFile(cfgFile)
		if err := v.ReadInConfig(); err != nil {
			return nil, fmt.Errorf("reading config file %s: %w", cfgFile, err)
		}
	} else {
		// Load project config (TRACKED) - qwex.yaml in current directory
		for _, name := range []string{"qwex.yaml", "qwex.yml", ".qwex.yaml"} {
			if _, err := os.Stat(name); err == nil {
				v.SetConfigFile(name)
				if err := v.ReadInConfig(); err == nil {
					break
				}
			}
		}

		// Merge local overrides (UNTRACKED) - .qwex/config.yaml
		localConfigPath := filepath.Join(ConfigRoot, "config.yaml")
		if _, err := os.Stat(localConfigPath); err == nil {
			v.SetConfigFile(localConfigPath)
			if err := v.MergeInConfig(); err != nil {
				return nil, fmt.Errorf("merging local config: %w", err)
			}
		}
	}

	// Set defaults
	setDefaults(v)

	// Unmarshal into Config
	var cfg Config
	if err := v.Unmarshal(&cfg); err != nil {
		return nil, fmt.Errorf("unmarshaling config: %w", err)
	}

	cfg.v = v
	return &cfg, nil
}

// Get returns a value from the underlying viper instance
// Useful for CLI flag binding and dynamic config access
func (c *Config) Get(key string) interface{} {
	if c.v == nil {
		return nil
	}
	return c.v.Get(key)
}

// GetString returns a string value from the underlying viper instance
func (c *Config) GetString(key string) string {
	if c.v == nil {
		return ""
	}
	return c.v.GetString(key)
}

// Viper returns the underlying viper instance
// Useful for advanced config operations
func (c *Config) Viper() *viper.Viper {
	return c.v
}

func setDefaults(v *viper.Viper) {
	if !v.IsSet(BaseUrlKey) {
		v.SetDefault(BaseUrlKey, "http://localhost:3000")
	} else {
		normalized := strings.TrimRight(v.GetString(BaseUrlKey), "/")
		v.Set(BaseUrlKey, normalized)
	}

	if !v.IsSet(ApiVersionKey) {
		v.SetDefault(ApiVersionKey, "v1")
	}
}

// ConfigFileUsed returns the config file that was used (if any)
func (c *Config) ConfigFileUsed() string {
	if c.v == nil {
		return ""
	}
	return c.v.ConfigFileUsed()
}
