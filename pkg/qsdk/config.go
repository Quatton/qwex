package qsdk

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/spf13/cobra"
	"github.com/spf13/viper"
)

type Config struct {
	BaseURL    string `mapstructure:"baseUrl"`
	APIVersion string `mapstructure:"apiVersion"`
}

const (
	EnvPrefix  = "QWEX"
	ConfigName = "qwex"
	ConfigRoot = ".qwex"

	BaseUrlKey    = "baseUrl"
	ApiVersionKey = "apiVersion"
)

func Initialize(cmd *cobra.Command, cfgFile string) error {
	viper.SetEnvPrefix(EnvPrefix)
	viper.SetEnvKeyReplacer(strings.NewReplacer(".", "_", "-", "_"))
	viper.AutomaticEnv()

	if cfgFile != "" {
		viper.SetConfigFile(cfgFile)
	} else {
		viper.AddConfigPath(ConfigRoot)
		if x := os.Getenv("XDG_CONFIG_HOME"); x != "" {
			viper.AddConfigPath(filepath.Join(x, ConfigName))
		}
		if home, err := os.UserHomeDir(); err == nil {
			viper.AddConfigPath(filepath.Join(home, ".config", ConfigName))
			viper.AddConfigPath(home)
		}
		viper.SetConfigName("config")
		viper.SetConfigType("yaml")
	}

	if err := viper.ReadInConfig(); err != nil {
		var notFound viper.ConfigFileNotFoundError
		if !errors.As(err, &notFound) {
			return fmt.Errorf("reading config: %w", err)
		}
	}

	// Read state file if it exists
	viper.AddConfigPath(ConfigRoot)
	viper.SetConfigName("state")
	viper.SetConfigType("yaml")

	// but if it doesn't exist, that's fine
	_ = viper.MergeInConfig()

	if cmd != nil {
		if err := viper.BindPFlags(cmd.Flags()); err != nil {
			return err
		}
	}

	if !viper.IsSet(BaseUrlKey) {
		viper.SetDefault(BaseUrlKey, "http://localhost:3000")
	} else {
		normalized := strings.TrimRight(viper.GetString(BaseUrlKey), "/")
		viper.Set(BaseUrlKey, normalized)
	}

	if !viper.IsSet(ApiVersionKey) {
		viper.SetDefault(ApiVersionKey, "v1")
	}

	return nil
}

func ConfigFileUsed() string {
	return viper.ConfigFileUsed()
}

func Viper() *viper.Viper {
	return viper.GetViper()
}

func GetConfig() (*Config, error) {
	var cfg Config
	if err := viper.Unmarshal(&cfg); err != nil {
		return nil, fmt.Errorf("unmarshaling config: %w", err)
	}
	return &cfg, nil
}
