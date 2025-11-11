package cmd

import (
	"fmt"
	"os"
	"os/exec"

	"github.com/spf13/cobra"
)

var sshCmd = &cobra.Command{
	Use:   "ssh [ssh options] [user@]hostname [command]",
	Short: "SSH to a host with optional workspace mounting",
	Long: `Connect to a remote host via SSH with all standard SSH options.
The -m flag can be used to specify mount paths (local:remote) for workspace-aware execution.

Examples:
  qwex ssh user@hostname
  qwex ssh -m ./data:/remote/data user@hostname
  qwex ssh -i ~/.ssh/key -p 2222 -m ./code:/workspace user@hostname
  qwex ssh user@hostname "ls -la"`,
	DisableFlagParsing:    true, // Let us handle all flags manually to pass through to ssh
	DisableFlagsInUseLine: true,
	Run: func(cmd *cobra.Command, args []string) {
		if len(args) == 0 {
			fmt.Fprintln(os.Stderr, "Error: hostname required")
			os.Exit(1)
		}

		// Parse our custom -m and -w flags before passing to ssh
		var sshArgs []string
		var mounts []string
		var workdir string

		i := 0
		for i < len(args) {
			if args[i] == "-m" && i+1 < len(args) {
				mounts = append(mounts, args[i+1])
				i += 2
			} else if args[i] == "-w" && i+1 < len(args) {
				workdir = args[i+1]
				i += 2
			} else {
				sshArgs = append(sshArgs, args[i])
				i++
			}
		}

		// TODO: Implement workspace mounting with the mounts
		if len(mounts) > 0 {
			fmt.Printf("Note: Mount paths specified but not yet implemented: %v\n", mounts)
		}

		// If -w is set, prepend 'cd <workdir> &&' to the remote command
		if workdir != "" {
			// Find the remote command (last argument)
			for idx, arg := range sshArgs {
				// Only wrap if it's not a flag and not user@host
				if idx > 0 && !isFlag(arg) && !containsColon(arg) {
					sshArgs[idx] = fmt.Sprintf("cd %s && %s", workdir, arg)
					break
				}
			}
		}

		// Execute ssh with the remaining arguments
		sshBin, err := exec.LookPath("ssh")
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error: ssh command not found: %v\n", err)
			os.Exit(1)
		}

		sshExec := exec.Command(sshBin, sshArgs...)
		sshExec.Stdin = os.Stdin
		sshExec.Stdout = os.Stdout
		sshExec.Stderr = os.Stderr

		if err := sshExec.Run(); err != nil {
			if exitErr, ok := err.(*exec.ExitError); ok {
				os.Exit(exitErr.ExitCode())
			}
			fmt.Fprintf(os.Stderr, "Error executing ssh: %v\n", err)
			os.Exit(1)
		}
	},
}

func init() {
	rootCmd.AddCommand(sshCmd)
}

// Helper to check if argument is a flag
func isFlag(s string) bool {
	return len(s) > 0 && s[0] == '-'
}

// Helper to check if argument is a mount spec
func containsColon(s string) bool {
	return len(s) > 0 && (s[0] == ':' || (len(s) > 1 && s[1] == ':'))
}
