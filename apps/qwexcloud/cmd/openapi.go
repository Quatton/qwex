package cmd

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/quatton/qwex/pkg/qapi"
	"github.com/quatton/qwex/pkg/qapi/routes"
	"github.com/spf13/cobra"
)

// openapiCmd represents the openapi command
var openapiCmd = &cobra.Command{
	Use:     "openapi",
	Aliases: []string{"spec"},
	Short:   "Generate OpenAPI specification",
	Long:    `Outputs the OpenAPI 3.0 specification for the Qwex Cloud API without requiring database or service initialization.`,
	Run:     generateOpenAPI,
}

var (
	openapiOutput    string
	openapiDowngrade bool
)

func init() {
	rootCmd.AddCommand(openapiCmd)
	// Flags
	openapiCmd.Flags().StringVarP(&openapiOutput, "output", "o", "", "Write output to file (default stdout)")
	openapiCmd.Flags().BoolVar(&openapiDowngrade, "downgrade", true, "Downgrade OpenAPI to 3.0 when generating the spec")
}

func generateOpenAPI(cmd *cobra.Command, args []string) {
	api := qapi.NewApi()
	routes.RegisterAPI(api.Api, nil)

	var (
		spec []byte
		err  error
	)

	if openapiDowngrade {
		spec, err = api.Api.OpenAPI().Downgrade()
	} else {
		// Marshal the OpenAPI structure directly to JSON (no downgrade)
		spec, err = json.Marshal(api.Api.OpenAPI())
	}

	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to generate OpenAPI spec: %v\n", err)
		os.Exit(1)
	}

	if openapiOutput == "" {
		fmt.Println(string(spec))
		return
	}

	if err := os.WriteFile(openapiOutput, spec, 0644); err != nil {
		fmt.Fprintf(os.Stderr, "Failed to write OpenAPI spec to %s: %v\n", openapiOutput, err)
		os.Exit(1)
	}
}
