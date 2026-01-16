package cmd

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/exec"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/Quatton/qwex/apps/qwexctl/internal/connect"
	"github.com/Quatton/qwex/apps/qwexctl/internal/pods"
	"github.com/radovskyb/watcher"
	"github.com/spf13/cobra"
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
		go startWatcher(localRepoPath)

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

		child.Stdin = os.Stdin
		child.Stdout = os.Stdout
		child.Stderr = os.Stderr

		if err != nil {
			log.Fatal(err)
		}

		done := make(chan struct{})

		c := make(chan os.Signal, 1)
		signal.Notify(c, os.Interrupt, syscall.SIGTERM)
		go func() {
			select {
			case <-c:
				child.Process.Kill()
				os.Exit(1)
			case <-done:
				return
			}
		}()

		if err := child.Start(); err != nil {
			log.Fatal(err)
		}

		go func() {
			mu.Lock()
			dirty := isDirty
			mu.Unlock()

			if dirty {
				err := connectService.SyncOnce(ctx)
				if err != nil && err.Error() != "up_to_date" {
				} else {
					mu.Lock()
					isDirty = false
					mu.Unlock()
				}
			}
		}()

		err = child.Wait()
		close(done)
		return nil
	},
}

func init() {
	rootCmd.AddCommand(execCmd)
}

func startWatcher(dir string) {
	w := watcher.New()
	w.SetMaxEvents(1)
	w.FilterOps(watcher.Write, watcher.Create, watcher.Remove, watcher.Rename, watcher.Move, watcher.Chmod)

	go func() {
		for {
			select {
			case <-w.Event:
				mu.Lock()
				isDirty = true
				mu.Unlock()
			case err := <-w.Error:
				log.Fatalln("Watcher error:", err)
			case <-w.Closed:
				return
			}
		}
	}()

	w.Ignore(".git")
	ignoreFiles := []string{".qwexignore", ".gitignore", ".dockerignore"}
	for _, fname := range ignoreFiles {
		data, err := os.ReadFile(fname)
		if err == nil {
			for _, line := range strings.FieldsFunc(string(data), func(r rune) bool { return r == '\n' || r == '\r' }) {
				w.Ignore(strings.TrimSpace(line))
			}
		}
	}

	if err := w.AddRecursive(dir); err != nil {
		log.Fatalln("Failed to add directory to watcher:", err)
	}

	if err := w.Start(500 * time.Millisecond); err != nil {
		log.Fatalln("Failed to start watcher:", err)
	}
}
