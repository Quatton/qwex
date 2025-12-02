"""Git operations for storage"""

from __future__ import annotations

import subprocess
from pathlib import Path


def git_push_to_remote(
    local_repo: Path,
    remote_url: str,
    ref: str = "HEAD",
) -> bool:
    """Push current HEAD to a remote bare repo.

    Args:
        local_repo: Local git repository path
        remote_url: SSH URL like 'csc:~/.qwex/repos/myproject.git'
        ref: Git ref to push (default HEAD)

    Returns:
        True if successful
    """
    result = subprocess.run(
        ["git", "push", "--force", remote_url, f"{ref}:refs/heads/main"],
        cwd=local_repo,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def ensure_bare_repo_exists(
    ssh_host: str,
    repo_path: str,
) -> bool:
    """Ensure a bare git repo exists on remote via SSH.

    Args:
        ssh_host: SSH host (can be an alias like 'csc')
        repo_path: Path on remote (e.g., '~/.qwex/repos/myproject.git')

    Returns:
        True if successful
    """
    # Create parent dir and init bare repo if it doesn't exist
    cmd = (
        f"mkdir -p {repo_path} && cd {repo_path} && git init --bare 2>/dev/null || true"
    )
    result = subprocess.run(
        ["ssh", ssh_host, cmd],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def get_remote_url(ssh_host: str, repo_path: str) -> str:
    """Build SSH remote URL.

    Args:
        ssh_host: SSH host (can be an alias like 'csc')
        repo_path: Path on remote

    Returns:
        SSH URL like 'csc:~/.qwex/repos/myproject.git'
    """
    return f"{ssh_host}:{repo_path}"
