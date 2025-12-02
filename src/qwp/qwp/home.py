"""QWEX_HOME resolution and directory structure"""

from __future__ import annotations

import os
from pathlib import Path
from typing import NamedTuple


class QwexHome(NamedTuple):
    """Resolved QWEX_HOME paths"""

    root: Path  # $QWEX_HOME

    @property
    def repos(self) -> Path:
        """$QWEX_HOME/repos/ - bare git repo caches"""
        return self.root / "repos"

    @property
    def spaces(self) -> Path:
        """$QWEX_HOME/spaces/ - ephemeral worktree checkouts"""
        return self.root / "spaces"

    @property
    def runs(self) -> Path:
        """$QWEX_HOME/runs/ - run outputs (logs, status, artifacts)"""
        return self.root / "runs"

    def run_dir(self, run_id: str) -> Path:
        """$QWEX_HOME/runs/<run-id>/"""
        return self.runs / run_id

    def space_dir(self, run_id: str) -> Path:
        """$QWEX_HOME/spaces/<run-id>/"""
        return self.spaces / run_id

    def repo_path(self, workspace_name: str) -> Path:
        """$QWEX_HOME/repos/<workspace-name>.git"""
        return self.repos / f"{workspace_name}.git"

    def ensure_dirs(self) -> None:
        """Create all necessary directories"""
        self.repos.mkdir(parents=True, exist_ok=True)
        self.spaces.mkdir(parents=True, exist_ok=True)
        self.runs.mkdir(parents=True, exist_ok=True)


def resolve_qwex_home(
    layer_override: str | None = None,
    workspace_root: Path | None = None,
) -> QwexHome:
    """
    Resolve QWEX_HOME with priority:
    1. Layer override (e.g., ssh.qwex_home)
    2. QWEX_HOME environment variable
    3. .qwex in workspace root (if workspace_root provided)
    4. ~/.qwex (default)

    Args:
        layer_override: Explicit path from layer config
        workspace_root: Path to workspace root (for .qwex fallback)

    Returns:
        Resolved QwexHome
    """
    # 1. Layer override
    if layer_override:
        return QwexHome(root=Path(layer_override).expanduser())

    # 2. Environment variable
    env_home = os.environ.get("QWEX_HOME")
    if env_home:
        return QwexHome(root=Path(env_home).expanduser())

    # 3. Workspace .qwex directory
    if workspace_root:
        return QwexHome(root=workspace_root / ".qwex")

    # 4. Default: ~/.qwex
    return QwexHome(root=Path.home() / ".qwex")
