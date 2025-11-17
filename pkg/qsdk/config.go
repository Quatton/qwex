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
	BaseURL string `mapstructure:"base_url"`
}

const (
	envprefix  = "QWEX"
	configname = "qwex"

	BaseUrlKey = "base_url"
)

func Initialize(cmd *cobra.Command, cfgFile string) error {
	viper.SetEnvPrefix(envprefix)
	viper.SetEnvKeyReplacer(strings.NewReplacer(".", "_", "-", "_"))
	viper.AutomaticEnv()

	if cfgFile != "" {
		viper.SetConfigFile(cfgFile)
	} else {
		viper.AddConfigPath(".")
		if x := os.Getenv("XDG_CONFIG_HOME"); x != "" {
			viper.AddConfigPath(filepath.Join(x, configname))
		}
		if home, err := os.UserHomeDir(); err == nil {
			viper.AddConfigPath(filepath.Join(home, ".config", configname))
			viper.AddConfigPath(home)
		}
		viper.SetConfigName(configname)
		viper.SetConfigType("toml")
	}

	if err := viper.ReadInConfig(); err != nil {
		var notFound viper.ConfigFileNotFoundError
		if !errors.As(err, &notFound) {
			return fmt.Errorf("reading config: %w", err)
		}
	}

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
