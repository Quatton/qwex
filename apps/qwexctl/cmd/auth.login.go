package cmd

import (
	"fmt"
	"time"

	"github.com/quatton/qwex/pkg/client"
	"github.com/quatton/qwex/pkg/qauth"
	"github.com/quatton/qwex/pkg/qlog"
	"github.com/quatton/qwex/pkg/qsdk"
	"github.com/spf13/cobra"
	"github.com/spf13/viper"
)

var loginCmd = &cobra.Command{
	Use:   "login",
	Short: "Authenticate to the qwex control plane",
	Long: `Start an interactive login flow to authenticate with the qwex control plane.

Examples:
	# start the interactive browser-based login
	qwexctl auth login

	# use a token for non-interactive authentication
	qwexctl auth login --token <TOKEN>

Credentials will be stored in the local configuration for subsequent commands.`,
	Run: run,
}

func run(cmd *cobra.Command, args []string) {
	logger := qlog.NewDefault()
	
	client, err := client.NewClient(viper.GetString(qsdk.BaseUrlKey))
	if err != nil {
		logger.Fatal("failed to create client", "error", err)
		return
	}
	auth := qsdk.NewAuthClient(client)
	loginUrl, err := auth.InitiateLoginWithGithub()
	if err != nil {
		logger.Fatal("failed to initiate login", "error", err)
		return
	}
	fmt.Printf("Please open the following URL in your browser to complete login:\n%s\n", loginUrl)

	accessToken, refreshToken, err := auth.CompleteLoginInteractive()
	if err != nil {
		logger.Fatal("failed to complete login", "error", err)
		return
	}

	if uc, err := qauth.FromToken(accessToken); err == nil {
		expStr := "unknown"
		if uc.Exp > 0 {
			expStr = time.Unix(uc.Exp, 0).Format(time.RFC3339)
		}
		fmt.Printf("Logged in as: %s (@%s)\n", uc.Name, uc.Login)
		fmt.Printf("Token expires: %s\n", expStr)
	} else {
		logger.Warn("failed to parse token claims", "error", err)
	}

	if err := qsdk.SaveTokens(viper.GetString(qsdk.BaseUrlKey), accessToken, refreshToken); err != nil {
		logger.Warn("failed to save tokens", "error", err)
	} else {
		fmt.Println("Access token saved")
	}
}

func init() {
	authCmd.AddCommand(loginCmd)
}
