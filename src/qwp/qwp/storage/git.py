"""Git-direct storage backend"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from qwp.storage.base import Storage, storage


class GitDirectStorageConfig(BaseModel):
    type: Literal["git-direct"] = "git-direct"
    ssh_host: str
    qwex_home: str = "~/.qwex"  # remote QWEX_HOME, repos stored at {qwex_home}/repos

    @property
    def repos_path(self) -> str:
        return f"{self.qwex_home.rstrip('/')}/repos"


@storage
class GitDirectStorage(Storage):
    """Git-direct storage: push via SSH, pull is no-op (uses worktrees)"""

    def __init__(self, config: GitDirectStorageConfig):
        self.config = config

    def push(self, local_path: Path, remote_ref: str) -> None:
        repo_path = f"{self.config.repos_path}/{remote_ref}.git"
        _ensure_bare_repo_exists(self.config.ssh_host, repo_path)
        remote_url = f"{self.config.ssh_host}:{repo_path}"
        _git_push_to_remote(local_path, remote_url)

    def pull(self, remote_ref: str, local_path: Path) -> None:
        pass

    @property
    def name(self) -> str:
        return f"GitDirectStorage({self.config.ssh_host})"


def _git_push_to_remote(local_repo: Path, remote_url: str, ref: str = "HEAD") -> bool:
    result = subprocess.run(
        ["git", "push", "--force", remote_url, f"{ref}:refs/heads/main"],
        cwd=local_repo,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _ensure_bare_repo_exists(ssh_host: str, repo_path: str) -> bool:
    cmd = (
        f"mkdir -p {repo_path} && cd {repo_path} && git init --bare 2>/dev/null || true"
    )
    result = subprocess.run(["ssh", ssh_host, cmd], capture_output=True, text=True)
    return result.returncode == 0
