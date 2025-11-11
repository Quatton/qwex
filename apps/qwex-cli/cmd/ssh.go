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
		// Parse --venv flag
		var venvPath string
		if len(args) == 0 {
			fmt.Fprintln(os.Stderr, "Error: hostname required")
			os.Exit(1)
		}

		// Parse our custom -m, -w, and --venv flags before passing to ssh
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
			} else if args[i] == "--venv" && i+1 < len(args) {
				venvPath = args[i+1]
				i += 2
			} else {
				sshArgs = append(sshArgs, args[i])
				i++
			}
		}

		// Default venv path if not specified
		if venvPath == "" {
			if workdir != "" {
				venvPath = fmt.Sprintf("%s/.venv", workdir)
			} else {
				venvPath = ".venv"
			}
		}

		// Run rsync for each mount before SSH
		if len(mounts) > 0 {
			userHost := ""
			for _, arg := range sshArgs {
				if userHost == "" && !isFlag(arg) && !containsColon(arg) {
					userHost = arg
				}
			}
			for _, m := range mounts {
				local, remote, err := parseMount(m)
				if err != nil {
					fmt.Fprintf(os.Stderr, "Invalid mount spec: %s\n", m)
					os.Exit(1)
				}
				if userHost == "" {
					fmt.Fprintln(os.Stderr, "Error: Could not determine user@host for rsync")
					os.Exit(1)
				}
				fmt.Printf("Syncing %s to %s:%s ...\n", local, userHost, remote)
				rsCmd := exec.Command("rsync", "-az", local+"/", userHost+":"+remote+"/")
				rsCmd.Stdout = os.Stdout
				rsCmd.Stderr = os.Stderr
				if err := rsCmd.Run(); err != nil {
					fmt.Fprintf(os.Stderr, "Error running rsync: %v\n", err)
					os.Exit(1)
				}
			}
		}

		// If -w is set, prepend 'mkdir -p <workdir> && cd <workdir> &&' to the remote command
		// If --venv is set (or default), prepend 'source <venv>/bin/activate &&' to the remote command
		if workdir != "" {
			for idx, arg := range sshArgs {
				if idx > 0 && !isFlag(arg) && !containsColon(arg) {
					// Compose the remote command
					remoteCmd := fmt.Sprintf("mkdir -p %s && cd %s && ", workdir, workdir)
					if venvPath != "" {
						remoteCmd += fmt.Sprintf("source %s/bin/activate 2>/dev/null; ", venvPath)
					}
					remoteCmd += arg
					sshArgs[idx] = remoteCmd
					break
				}
			}
		} else if venvPath != "" {
			for idx, arg := range sshArgs {
				if idx > 0 && !isFlag(arg) && !containsColon(arg) {
					remoteCmd := fmt.Sprintf("source %s/bin/activate 2>/dev/null; %s", venvPath, arg)
					sshArgs[idx] = remoteCmd
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

// Helper to parse mount string "local:remote"
func parseMount(m string) (string, string, error) {
	split := 0
	for i := 0; i < len(m); i++ {
		if m[i] == ':' {
			split = i
			break
		}
	}
	if split == 0 || split == len(m)-1 {
		return "", "", fmt.Errorf("invalid mount: %s", m)
	}
	return m[:split], m[split+1:], nil
}
