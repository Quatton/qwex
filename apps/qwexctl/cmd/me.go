package cmd

import (
	"context"
	"fmt"
	"log"

	"github.com/quatton/qwex/pkg/qsdk"
	"github.com/spf13/cobra"
)

var meCmd = &cobra.Command{
	Use:   "me",
	Short: "Show information about the current authenticated user",
	Run: func(cmd *cobra.Command, args []string) {
		sdk, err := qsdk.NewSdk()
		if err != nil {
			log.Fatalf("failed to initialize SDK: %v", err)
		}

		resp, err := sdk.Client.GetMeWithResponse(context.Background())
		if err != nil {
			log.Fatalf("api request failed: %v", err)
		}
		if resp.JSON200 == nil {
			log.Fatalf("unexpected response: status=%d body=%s", resp.StatusCode(), string(resp.Body))
		}

		u := resp.JSON200.User
		fmt.Printf("Logged in: %s (@%s)\n", u.Name, u.Login)
		fmt.Printf("Email: %s\n", u.Email)
		fmt.Printf("ID: %s\n", u.Id)
	},
}

func init() {
	rootCmd.AddCommand(meCmd)
}
