"""QWEX_HOME resolution and directory structure"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import NamedTuple

log = logging.getLogger(__name__)


class QwexHome(NamedTuple):
    """
    Resolved QWEX_HOME paths.

    Structure:
        $QWEX_HOME/
        ├── workspaces/<workspace-name>/
        │   ├── runs/       # run outputs (logs, status)
        │   ├── spaces/     # ephemeral worktree checkouts
        │   └── repos/      # bare git repo cache (for remote)
        └── logs/           # qwex internal logs (future)
    """

    root: Path  # $QWEX_HOME (default: ~/.qwex)
    workspace_name: str | None = None  # resolved workspace name

    @property
    def workspaces(self) -> Path:
        """$QWEX_HOME/workspaces/"""
        return self.root / "workspaces"

    def workspace_dir(self, name: str | None = None) -> Path:
        """$QWEX_HOME/workspaces/<workspace-name>/"""
        ws_name = name or self.workspace_name
        if not ws_name:
            raise ValueError("workspace_name required")
        return self.workspaces / ws_name

    def runs(self, workspace: str | None = None) -> Path:
        """$QWEX_HOME/workspaces/<workspace>/runs/"""
        return self.workspace_dir(workspace) / "runs"

    def spaces(self, workspace: str | None = None) -> Path:
        """$QWEX_HOME/workspaces/<workspace>/spaces/"""
        return self.workspace_dir(workspace) / "spaces"

    def repos(self, workspace: str | None = None) -> Path:
        """$QWEX_HOME/workspaces/<workspace>/repos/"""
        return self.workspace_dir(workspace) / "repos"

    def run_dir(self, run_id: str, workspace: str | None = None) -> Path:
        """$QWEX_HOME/workspaces/<workspace>/runs/<run-id>/"""
        return self.runs(workspace) / run_id

    def space_dir(self, run_id: str, workspace: str | None = None) -> Path:
        """$QWEX_HOME/workspaces/<workspace>/spaces/<run-id>/"""
        return self.spaces(workspace) / run_id

    def ensure_dirs(self, workspace: str | None = None) -> None:
        """Create all necessary directories for a workspace"""
        ws = workspace or self.workspace_name
        if not ws:
            raise ValueError("workspace_name required")
        self.runs(ws).mkdir(parents=True, exist_ok=True)
        self.spaces(ws).mkdir(parents=True, exist_ok=True)
        self.repos(ws).mkdir(parents=True, exist_ok=True)
        log.debug(
            f"Ensured directories for workspace '{ws}' at {self.workspace_dir(ws)}"
        )

    def ensure_workspace_symlink(
        self, workspace_root: Path, workspace: str | None = None
    ) -> Path:
        """
        Ensure .qwex symlink in workspace points to QWEX_HOME/workspaces/<name>.

        Returns the symlink path.
        """
        ws = workspace or self.workspace_name
        if not ws:
            raise ValueError("workspace_name required")

        target = self.workspace_dir(ws)
        symlink = workspace_root / ".qwex"

        # Ensure target exists
        target.mkdir(parents=True, exist_ok=True)

        if symlink.is_symlink():
            current_target = symlink.resolve()
            if current_target == target.resolve():
                log.debug(f"Symlink {symlink} already points to {target}")
                return symlink
            # Remove old symlink
            symlink.unlink()
            log.debug(f"Removed old symlink {symlink} -> {current_target}")
        elif symlink.exists():
            # It's a real directory, not a symlink
            # TODO: migrate existing data?
            log.warning(f"{symlink} is a directory, not a symlink. Consider migrating.")
            return symlink

        symlink.symlink_to(target)
        log.info(f"Created symlink {symlink} -> {target}")
        return symlink


def resolve_qwex_home(
    config_override: str | None = None,
    layer_override: str | None = None,
    workspace_name: str | None = None,
) -> QwexHome:
    """
    Resolve QWEX_HOME.

    Priority:
    1. Layer override (e.g., ssh.qwex_home for remote)
    2. Config override (from qwex.yaml settings.home)
    3. QWEX_HOME environment variable
    4. ~/.qwex (default)

    Args:
        config_override: Explicit path from qwex.yaml settings.home
        layer_override: Explicit path from layer config (highest priority)
        workspace_name: Workspace name for workspace-specific paths

    Returns:
        Resolved QwexHome
    """
    # 1. Layer override (highest priority for remote execution)
    if layer_override:
        root = Path(layer_override).expanduser()
        log.debug(f"Using layer override QWEX_HOME: {root}")
        return QwexHome(root=root, workspace_name=workspace_name)

    # 2. Config override
    if config_override:
        root = Path(config_override).expanduser()
        log.debug(f"Using config QWEX_HOME: {root}")
        return QwexHome(root=root, workspace_name=workspace_name)

    # 3. Environment variable
    env_home = os.environ.get("QWEX_HOME")
    if env_home:
        root = Path(env_home).expanduser()
        log.debug(f"Using QWEX_HOME from env: {root}")
        return QwexHome(root=root, workspace_name=workspace_name)

    # 4. Default: ~/.qwex
    root = Path.home() / ".qwex"
    log.debug(f"Using default QWEX_HOME: {root}")
    return QwexHome(root=root, workspace_name=workspace_name)
