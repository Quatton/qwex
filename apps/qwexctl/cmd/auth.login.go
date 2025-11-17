/*
Copyright © 2025 NAME HERE <EMAIL ADDRESS>
*/
package cmd

import (
	"fmt"
	"log"

	"github.com/quatton/qwex/pkg/client"
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
	fmt.Printf("Login successful! Token: %s\n", token)
}

func init() {
	authCmd.AddCommand(loginCmd)
}
