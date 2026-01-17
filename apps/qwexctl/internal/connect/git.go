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

func (s *Service) IsStatusClean(ctx context.Context) (bool, error) {
	cmd := []string{"git", "-C", "/workspace", "status", "--porcelain"}

	output, err := s.RemoteExec(ctx, cmd, nil)
	if err != nil {
		return false, fmt.Errorf("remote git status failed: %s", output.Stderr)
	}

	if strings.TrimSpace(output.Stdout) == "" {
		return true, nil
	}

	return false, nil
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
	tmpIndex, err := os.CreateTemp("", "qwex-git-index-*")
	if err != nil {
		return "", "", err
	}
	tmpIndexPath := tmpIndex.Name()
	tmpIndex.Close()
	defer os.Remove(tmpIndexPath)

	env := os.Environ()
	env = append(env, fmt.Sprintf("GIT_INDEX_FILE=%s", tmpIndexPath))

	cmd := exec.Command("git", "-C", s.LocalRepoPath, "read-tree", "HEAD")
	cmd.Env = env

	if out, err := cmd.CombinedOutput(); err != nil {
		return "", "", fmt.Errorf("read-tree failed: %s %v", out, err)
	}

	cmd = exec.Command("git", "-C", s.LocalRepoPath, "add", "-A")
	cmd.Env = env
	if out, err := cmd.CombinedOutput(); err != nil {
		return "", "", fmt.Errorf("git add -A failed: %s %v", out, err)
	}

	cmd = exec.Command("git", "-C", s.LocalRepoPath, "write-tree")
	cmd.Env = env
	out, err := cmd.Output()
	if err != nil {
		return "", "", fmt.Errorf("write-tree failed: %v", err)
	}
	treeHash := strings.TrimSpace(string(out))

	// NOTE: very rare fallback. this is to be consistent with previous behavior
	if treeHash == "" {
		out, _ = exec.Command("git", "rev-parse", "HEAD").Output()
		treeHash = strings.TrimSpace(string(out))

		treeCmd := exec.Command("git", "rev-parse", fmt.Sprintf("%s^{tree}", treeHash))
		out, err = treeCmd.Output()
		treeHash = strings.TrimSpace(string(out))
	}

	if remote != nil && treeHash == remote.TreeHash {
		return "", "", fmt.Errorf("up_to_date")
	}

	commitMsg := "Qwex snapshot: WIP changes with untracked files"

	cmd = exec.Command("git", "-C", s.LocalRepoPath, "commit-tree", treeHash, "-p", "HEAD", "-m", commitMsg)
	out, err = cmd.Output()
	if err != nil {
		return "", "", fmt.Errorf("commit-tree failed: %v", err)
	}

	targetHash := strings.TrimSpace(string(out))

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
