package connect

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/exec"
	"strings"
)

type RemoteState struct {
	CommitHash string
	TreeHash   string
}

func (s *Service) GetRemoteHead(ctx context.Context) (*RemoteState, error) {
	cmd := []string{"git", "-C", "/workspace", "rev-parse", "HEAD", "HEAD^{tree}"}

	output, err := s.RemoteExec(ctx, cmd, nil)

	if output == nil {
		return nil, err
	}

	if err != nil {
		return nil, fmt.Errorf("remote HEAD fetch failed: %s", output.Stderr)
	}

	lines := strings.Fields(output.Stdout)

	if len(lines) < 2 {
		return nil, nil
	}

	return &RemoteState{
		CommitHash: lines[0],
		TreeHash:   lines[1],
	}, nil
}

func (s *Service) SendBundle(ctx context.Context, bundlePath string, targetHash string) error {
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
		if output != nil {
			log.Printf("Remote sync failed: %v | Stdout: %s | Stderr: %s", err, output.Stdout, output.Stderr)
		} else {
			log.Printf("Remote sync failed to start: %v", err)
		}
	}
	return nil
}

func (s *Service) forceCreateBundle(targetHash, remoteHash string) (string, error) {
	bundleFilePath := "/tmp/repo.bundle"
	tempRef := "refs/qwex/temp-sync"
	if err := exec.Command("git", "update-ref", tempRef, targetHash).Run(); err != nil {
		return "", fmt.Errorf("failed to create temp ref: %w", err)
	}
	defer exec.Command("git", "update-ref", "-d", tempRef).Run()

	var args []string
	args = append(args, "-C", s.LocalRepoPath, "bundle", "create", bundleFilePath, tempRef)

	if remoteHash != "" {
		args = append(args, fmt.Sprintf("^%s", remoteHash))
	}

	out, err := exec.Command("git", args...).CombinedOutput()

	if err != nil {
		return "", fmt.Errorf("failed to create git bundle: %s", string(out))
	}

	return bundleFilePath, nil
}

func (s *Service) CreateGitBundle(remote *RemoteState) (string, string, error) {
	stashOutput := exec.Command("git", "-C", s.LocalRepoPath, "stash", "create", "--include-untracked")

	out, err := stashOutput.Output()
	if err != nil {
		stdErr := stashOutput.Stderr
		return "", "", fmt.Errorf("failed to create git stash: %s", stdErr)
	}

	targetHash := strings.TrimSpace(string(out))

	if targetHash == "" {
		out, _ = exec.Command("git", "rev-parse", "HEAD").Output()
		targetHash = strings.TrimSpace(string(out))
	}

	treeCmd := exec.Command("git", "rev-parse", fmt.Sprintf("%s^{tree}", targetHash))
	out, err = treeCmd.Output()
	localTreeHash := strings.TrimSpace(string(out))

	if remote != nil && localTreeHash == remote.TreeHash {
		return "", "", fmt.Errorf("up_to_date")
	}

	remoteHash := ""
	if remote != nil {
		remoteHash = remote.CommitHash
	}

	bundlePath, err := s.forceCreateBundle(targetHash, remoteHash)

	if err != nil {
		return "", "", err
	}

	return bundlePath, targetHash, nil
}
