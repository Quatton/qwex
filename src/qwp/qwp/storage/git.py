"""Git-direct storage backend"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from qwp.storage.base import Storage, register_storage


class GitDirectStorageConfig(BaseModel):
    """Configuration for git-direct storage"""

    type: Literal["git-direct"] = "git-direct"
    ssh_host: str  # SSH host (can be an alias like 'csc')
    base_path: str = "~/.qwex/repos"  # Base path for bare repos


@register_storage("git-direct")
class GitDirectStorage(Storage):
    """Git-direct storage: push via SSH to bare repos.

    This storage backend:
    - push: Force-pushes to a bare git repo on the remote
    - pull: No-op (assumes remote already has the code)

    Designed for SSH-based execution where the remote already
    has access to the pushed code via git worktrees.
    """

    def __init__(self, config: GitDirectStorageConfig):
        self.config = config

    def push(self, local_path: Path, remote_ref: str) -> None:
        """Push local repo to remote bare repo.

        Args:
            local_path: Local git repository path
            remote_ref: Repository name (e.g., 'myproject')
        """
        repo_path = f"{self.config.base_path}/{remote_ref}.git"

        # Ensure bare repo exists
        _ensure_bare_repo_exists(self.config.ssh_host, repo_path)

        # Push to remote
        remote_url = _get_remote_url(self.config.ssh_host, repo_path)
        _git_push_to_remote(local_path, remote_url)

    def pull(self, remote_ref: str, local_path: Path) -> None:
        """Pull is a no-op for git-direct storage.

        The remote execution environment uses git worktrees
        from the bare repo, so no explicit pull is needed.
        """
        pass

    @property
    def name(self) -> str:
        return f"GitDirectStorage({self.config.ssh_host})"


# Private helper functions


def _git_push_to_remote(
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


def _ensure_bare_repo_exists(
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
    cmd = (
        f"mkdir -p {repo_path} && cd {repo_path} && git init --bare 2>/dev/null || true"
    )
    result = subprocess.run(
        ["ssh", ssh_host, cmd],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _get_remote_url(ssh_host: str, repo_path: str) -> str:
    """Build SSH remote URL.

    Args:
        ssh_host: SSH host (can be an alias like 'csc')
        repo_path: Path on remote

    Returns:
        SSH URL like 'csc:~/.qwex/repos/myproject.git'
    """
    return f"{ssh_host}:{repo_path}"


# Re-export for backward compatibility (deprecate later)
git_push_to_remote = _git_push_to_remote
ensure_bare_repo_exists = _ensure_bare_repo_exists
get_remote_url = _get_remote_url
