/*
Copyright © 2025 NAME HERE <EMAIL ADDRESS>
*/
package cmd

import (
	"fmt"
	"log"
	"time"

	"github.com/quatton/qwex/pkg/client"
	"github.com/quatton/qwex/pkg/qsdk"
	"github.com/spf13/cobra"
	"github.com/spf13/viper"
	"github.com/zalando/go-keyring"
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
	client, err := client.NewClient(viper.GetString(qsdk.BaseUrlKey))
	if err != nil {
		log.Fatalf("failed to create client: %v", err)
		return
	}
	auth := qsdk.NewAuthClient(client)
	loginUrl, err := auth.InitiateLoginWithGithub()
	if err != nil {
		log.Fatalf("failed to initiate login: %v", err)
		return
	}
	fmt.Printf("Please open the following URL in your browser to complete login:\n%s\n", loginUrl)

	token, err := auth.CompleteLoginInteractive()
	if err != nil {
		log.Fatalf("failed to complete login: %v", err)
		return
	}

	if uc, err := qsdk.FromToken(token); err == nil {
		expStr := "unknown"
		if uc.Exp > 0 {
			expStr = time.Unix(uc.Exp, 0).Format(time.RFC3339)
		}
		fmt.Printf("Logged in as: %s (@%s)\n", uc.Name, uc.Login)
		fmt.Printf("Token expires: %s\n", expStr)
	} else {
		log.Printf("warning: failed to parse token claims: %v", err)
	}

	service := "qwex"
	user := viper.GetString(qsdk.BaseUrlKey)
	if user == "" {
		user = "default"
	}
	if err := keyring.Set(service, user, token); err != nil {
		log.Printf("warning: failed to save token to keyring: %v", err)
	} else {
		fmt.Println("Access token saved")
	}
}

func init() {
	authCmd.AddCommand(loginCmd)
}
