package cmd

import (
	"context"
	"os"
	"strings"

	"github.com/Quatton/qwex/apps/qwexctl/internal/k8s"
	"github.com/spf13/cobra"
	"github.com/spf13/viper"
)

var (
	cfgFile   string
	namespace string
)

type Service struct {
	K8s       *k8s.K8sClient
	Namespace string // Added to service so subcommands can find it easily
}

var rootCmd = &cobra.Command{
	Use:   "qwexctl",
	Short: "Queued Workspace-aware EXecutor",
	PersistentPreRunE: func(cmd *cobra.Command, args []string) error {
		globalService, err := initServiceManual()
		if err != nil {
			return err
		}
		ctx := context.WithValue(cmd.Context(), "service", globalService)
		cmd.SetContext(ctx)
		return nil
	},
}

func initServiceManual() (*Service, error) {
	ns := viper.GetString("namespace")

	k8sClient, err := k8s.NewK8sClient()
	if err != nil {
		return nil, err
	}

	globalService := &Service{
		K8s:       k8sClient,
		Namespace: ns,
	}

	return globalService, nil
}

func Execute() {
	if err := rootCmd.Execute(); err != nil {
		os.Exit(1)
	}
}

func init() {
	cobra.OnInitialize(initConfig)

	rootCmd.PersistentFlags().StringVar(&cfgFile, "config", "", "config file (default is $HOME/.qwexctl.yaml)")

	rootCmd.PersistentFlags().StringVarP(&namespace, "namespace", "n", "qwex-demo", "kubernetes namespace for dev environment")

	viper.BindPFlag("namespace", rootCmd.PersistentFlags().Lookup("namespace"))
}

func initConfig() {
	if cfgFile != "" {
		viper.SetConfigFile(cfgFile)
	} else {
		home, _ := os.UserHomeDir()
		viper.AddConfigPath(home)
		viper.SetConfigType("yaml")
		viper.SetConfigName(".qwexctl")
	}

	viper.SetEnvPrefix("QWEX")
	viper.SetEnvKeyReplacer(strings.NewReplacer("-", "_"))
	viper.AutomaticEnv()

	if err := viper.ReadInConfig(); err == nil {
		// log.Println("Using config file:", viper.ConfigFileUsed())
	}
}
