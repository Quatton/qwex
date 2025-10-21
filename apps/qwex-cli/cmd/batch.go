package cmd

import (
	"fmt"

	"github.com/spf13/cobra"
)

var batchCmd = &cobra.Command{
	Use:   "batch [command]",
	Short: "Submit a batch job to run on the cluster",
	Long: `Submit a command to run as a batch job on the cluster.
The job will be queued and executed when resources are available.

Example:
  qwex batch python train.py
  qwex batch -- python main.py --flag value`,
	Args: cobra.MinimumNArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		// TODO: Implement batch job submission
		fmt.Printf("Submitting batch job: %v\n", args)
		fmt.Println("This will communicate with the FastAPI controller to create a Kueue workload")
	},
}

func init() {
	rootCmd.AddCommand(batchCmd)

	// Add flags for batch command
	// batchCmd.Flags().StringP("queue", "q", "default", "Queue name")
	// batchCmd.Flags().IntP("cpu", "c", 1, "Number of CPUs")
	// batchCmd.Flags().StringP("memory", "m", "1Gi", "Memory limit")
}
