package utils

import (
	"os"
	"os/exec"
	"runtime"
	"syscall"
)

// Courtesy of Gemini I have no idea if this is actually cross-platform safe
// ReplaceProcess replaces the current Go process with the given command.
// On Windows, it falls back to running as a child process (since syscall.Exec is missing).
func ReplaceProcess(command string, args []string) error {
	binary, err := exec.LookPath(command)
	if err != nil {
		return err
	}

	// Windows fallback (Standard Child Process)
	if runtime.GOOS == "windows" {
		cmd := exec.Command(binary, args[1:]...) // args[0] is typically the binary name
		cmd.Stdin = os.Stdin
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
		return cmd.Run()
	}

	// Linux/Mac (True Process Replacement)
	// This preserves TTY, PID, and signal handling perfectly.
	return syscall.Exec(binary, args, os.Environ())
}
