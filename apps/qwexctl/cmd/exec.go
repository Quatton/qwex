package cmd

import (
	"context"
	"fmt"
	"io"
	"log"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"slices"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/Quatton/qwex/apps/qwexctl/internal/connect"
	"github.com/Quatton/qwex/apps/qwexctl/internal/pods"
	"github.com/fsnotify/fsnotify"
	"github.com/go-git/go-billy/v5/osfs"
	"github.com/go-git/go-git/v5/plumbing/format/gitignore"
	"github.com/spf13/cobra"

	"github.com/creack/pty"
	"golang.org/x/term"
)

var (
	isDirty bool
	mu      sync.Mutex
)

var execCmd = &cobra.Command{
	Use:                "exec -- [command]",
	Short:              "Execute a command on the remote workspace (Syncs first)",
	DisableFlagParsing: true,
	RunE: func(cmd *cobra.Command, args []string) error {
		localRepoPath := connect.GetLocalRepoPath(cfgFile)

		watcher, err := startWatcher(localRepoPath)
		if err != nil {
			return err
		}
		defer watcher.Close()

		svc, err := initServiceManual()
		if err != nil {
			return err
		}
		ctx := cmd.Context()

		podService := &pods.Service{K8s: svc.K8s.Clientset, Namespace: svc.Namespace}
		dep, err := podService.GetOrCreateDevelopmentDeployment(ctx, pods.Active)
		if err != nil {
			return err
		}

		pod, err := podService.GetPodFromDeployment(ctx, dep)
		if err != nil {
			return err
		}

		connectService := connect.NewService(svc.K8s.Clientset, svc.K8s.Config, namespace, pod.Name, pods.SyncContainerName, localRepoPath)

		ctx, cancel := context.WithCancel(cmd.Context())
		defer cancel()

		if err := connectService.SyncOnce(ctx); err != nil && err.Error() != "up_to_date" {
			return fmt.Errorf("pre-execution sync failed: %w", err)
		}

		if args[0] == "--" {
			args = args[1:]
		}

		if len(args) == 1 && (strings.Contains(args[0], "bash") || strings.Contains(args[0], "sh")) {
			relativeDir, err := exec.Command("git", "rev-parse", "--show-prefix").Output()

			if err == nil {
				dir := strings.TrimSpace(string(relativeDir))
				if dir != "" {
					log.Printf("Changing to workspace subdirectory: %s", dir)
					args = append([]string{args[0], "-c", fmt.Sprintf("cd %s && exec %s", dir, strings.Join(args, " "))}, args[1:]...)
				}
			} else {
				log.Printf("Could not determine git relative path: %v", err)
			}
		}

		kubectlArgs := []string{"exec", "-i", "-t"}
		kubectlArgs = append(kubectlArgs, "-n", svc.Namespace)
		kubectlArgs = append(kubectlArgs, pod.Name)
		kubectlArgs = append(kubectlArgs, "-c", pods.DevContainerName)
		kubectlArgs = append(kubectlArgs, "--")
		kubectlArgs = append(kubectlArgs, args...)

		fmt.Printf("🚀 Connecting to %s...\n", pod.Name)

		child := exec.Command("kubectl", kubectlArgs...)

		// We have to manually open PTY and not use pty.Start because
		// kubectl will complain that Setctty set but Ctty not valid in child
		ptmx, tty, err := pty.Open()
		if err != nil {
			return fmt.Errorf("failed to open pty: %w", err)
		}
		defer func() { _ = ptmx.Close() }()

		child.Stderr = tty
		child.Stdout = tty
		child.Stdin = tty

		if err := child.Start(); err != nil {
			tty.Close()
			return fmt.Errorf("failed to start child: %w", err)
		}

		if err != nil {
			log.Fatal(err)
		}

		// (apparently? told by mr gemini pro)
		// CRITICAL: Close the slave TTY in the parent immediately after Start.
		// The child process now owns it. If we don't close it here,
		// the process might never exit correctly.
		_ = tty.Close()

		ch := make(chan os.Signal, 1)
		signal.Notify(ch, syscall.SIGWINCH)
		go func() {
			for range ch {
				if err := pty.InheritSize(os.Stdin, ptmx); err != nil {
					log.Printf("error resizing pty: %s", err)
				}
			}
		}()
		ch <- syscall.SIGWINCH

		oldState, err := term.MakeRaw(int(os.Stdin.Fd()))
		if err != nil {
			return fmt.Errorf("failed to set raw mode: %w", err)
		}
		defer func() { _ = term.Restore(int(os.Stdin.Fd()), oldState) }()

		go func() {
			buf := make([]byte, 1024)
			for {
				n, err := os.Stdin.Read(buf)
				if err != nil {
					return
				}

				input := buf[:n]

				isEnter := slices.Contains(input, '\r')

				if isEnter {
					mu.Lock()
					dirty := isDirty
					mu.Unlock()

					if dirty {
						ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
						err := connectService.SyncOnce(ctx)
						cancel()

						if err != nil && err.Error() != "up_to_date" {
							fmt.Fprintf(os.Stdout, "\r\n[qwex] Sync Error: %v\r\n", err)
						} else {
							mu.Lock()
							isDirty = false
							mu.Unlock()
						}
					}
				}

				_, err = ptmx.Write(input)
				if err != nil {
					return
				}
			}
		}()

		_, _ = io.Copy(os.Stdout, ptmx)

		_ = child.Wait()

		return nil
	},
}

func init() {
	rootCmd.AddCommand(execCmd)
}

func startWatcher(root string) (*fsnotify.Watcher, error) {
	w, err := fsnotify.NewWatcher()
	if err != nil {
		return nil, fmt.Errorf("failed to create watcher: %v", err)
	}

	absRoot, err := filepath.Abs(root)
	if err != nil {
		w.Close()
		return nil, err
	}

	err = watchRecursive(w, absRoot, []gitignore.Matcher{})
	if err != nil {
		w.Close()
		return nil, err
	}

	go func() {
		for {
			select {
			case event, ok := <-w.Events:
				if !ok {
					return
				}

				if event.Op&fsnotify.Create == fsnotify.Create {
					info, err := os.Stat(event.Name)
					if err == nil && info.IsDir() {
						_ = watchRecursive(w, event.Name, []gitignore.Matcher{})
					}
				}

				if event.Op&fsnotify.Write == fsnotify.Write ||
					event.Op&fsnotify.Create == fsnotify.Create ||
					event.Op&fsnotify.Remove == fsnotify.Remove ||
					event.Op&fsnotify.Rename == fsnotify.Rename {

					mu.Lock()
					isDirty = true
					mu.Unlock()
				}

			case err, ok := <-w.Errors:
				if !ok {
					return
				}
				log.Printf("Watcher error: %v", err)
			}
		}
	}()

	return w, nil
}

func watchRecursive(watcher *fsnotify.Watcher, dir string, parentMatchers []gitignore.Matcher) error {
	matchers := parentMatchers

	ignoreFile := filepath.Join(dir, ".gitignore")
	if _, err := os.Stat(ignoreFile); err == nil {
		ps, err := gitignore.ReadPatterns(osfs.New(dir), []string{".gitignore"})
		if err == nil {
			m := gitignore.NewMatcher(ps)
			matchers = append(matchers, m)
		}
	}

	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil
	}

	for _, entry := range entries {
		name := entry.Name()
		fullPath := filepath.Join(dir, name)
		isDir := entry.IsDir()

		if name == ".git" {
			continue
		}

		if isIgnoredStack(matchers, fullPath, isDir) {
			continue
		}

		if isDir {
			err := watcher.Add(fullPath)
			if err != nil {
				// log.Printf("Failed to watch %s: %v", fullPath, err)
			}
			_ = watchRecursive(watcher, fullPath, matchers)
		}
	}

	return watcher.Add(dir)
}

func isIgnoredStack(matchers []gitignore.Matcher, path string, isDir bool) bool {
	pathParts := strings.Split(filepath.ToSlash(path), "/")
	for _, m := range matchers {
		if m.Match(pathParts, isDir) {
			return true
		}
	}
	return false
}
