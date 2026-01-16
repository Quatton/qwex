package connect

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/exec"
	"strings"
)

func (s *Service) GetRemoteHead(ctx context.Context) (string, error) {
	// Command: git -C /workspace rev-parse HEAD
	cmd := []string{"git", "-C", "/workspace", "rev-parse", "HEAD"}

	output, err := s.RemoteExec(ctx, cmd, nil)

	if err != nil {
		log.Printf("Remote head is empty")
		return "", nil
	}

	return strings.TrimSpace(output.Stdout), nil
}

func (s *Service) SendBundle(ctx context.Context, bundlePath string, targetHash string) error {

	log.Printf("Syncing to %s...", targetHash)

	file, err := os.Open(bundlePath)
	if err != nil {
		return err
	}
	defer file.Close()
	defer os.Remove(bundlePath)

	remoteScript := `
set -e
cat > /tmp/incoming.bundle
git -C /workspace fetch /tmp/incoming.bundle refs/qwex/temp-sync
git -C /workspace reset --hard FETCH_HEAD
echo "Sync Successful"
`

	cmd := []string{"/bin/sh", "-c", remoteScript}

	output, err := s.RemoteExec(ctx, cmd, file)

	if err != nil {
		log.Printf("remote sync failed: %s | %s", output.Stdout, output.Stderr)
		return err
	}

	return nil
}

func (s *Service) CreateGitBundle(fromHash string) (string, string, error) {
	stashOutput := exec.Command("git", "-C", s.LocalRepoPath, "stash", "create", "--include-untracked")
	out, err := stashOutput.Output()
	if err != nil {
		stdErr := stashOutput.Stderr
		log.Printf("Error creating stash: %s", stdErr)
		return "", "", err
	}
	targetHash := strings.TrimSpace(string(out))

	if targetHash == "" {
		out, _ = exec.Command("git", "rev-parse", "HEAD").Output()
		targetHash = strings.TrimSpace(string(out))
	}

	if fromHash == targetHash {
		return "", "", nil
	}

	bundleFilePath := "/tmp/repo.bundle"

	tempRef := "refs/qwex/temp-sync"

	if err := exec.Command("git", "update-ref", tempRef, targetHash).Run(); err != nil {
		return "", "", fmt.Errorf("failed to create temp ref: %w", err)
	}

	defer exec.Command("git", "update-ref", "-d", tempRef).Run()

	var args []string
	args = append(args, "-C", s.LocalRepoPath, "bundle", "create", bundleFilePath, tempRef)
	if fromHash != "" {
		args = append(args, fmt.Sprintf("^%s", fromHash))
	}

	out, err = exec.Command("git", args...).CombinedOutput()
	if err != nil {
		log.Printf("Error creating git bundle: %s", string(out))
		return "", "", err
	}

	return bundleFilePath, targetHash, nil
}

func (s *Service) Sync(ctx context.Context) error {
	remoteHash, err := s.GetRemoteHead(ctx)
	if err != nil {
		log.Fatalf("Error getting remote HEAD: %v\n", err)
		return err
	}

	bundleFile, targetHash, err := s.CreateGitBundle(remoteHash)
	if err != nil {
		log.Fatalf("Error creating git bundle: %v\n", err)
		return err
	}

	err = s.SendBundle(ctx, bundleFile, targetHash)
	if err != nil {
		log.Fatalf("Error sending git bundle: %v\n", err)
		return err
	}

	return nil
}
