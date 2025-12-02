"""Workspace utilities for qwex"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple


class Workspace(NamedTuple):
    """Represents a qwex workspace"""

    root: Path
    config_file: Path

    @property
    def qwex_dir(self) -> Path:
        """Get .qwex directory"""
        return self.root / ".qwex"

    @property
    def runs_dir(self) -> Path:
        """Get runs directory"""
        return self.qwex_dir / "runs"


def find_workspace(start: Path | None = None) -> Workspace | None:
    """
    Find workspace by walking up from start directory looking for qwex.yaml.

    Returns None if no workspace is found.
    """
    if start is None:
        start = Path.cwd()

    current = start.resolve()

    while current != current.parent:
        config_file = current / "qwex.yaml"
        if config_file.exists():
            return Workspace(root=current, config_file=config_file)

        # Also check for qwex.yml
        config_file = current / "qwex.yml"
        if config_file.exists():
            return Workspace(root=current, config_file=config_file)

        current = current.parent

    return None


def find_workspace_or_cwd(start: Path | None = None) -> Workspace:
    """
    Find workspace or fall back to current directory.

    If no qwex.yaml is found, uses cwd as root with no config file.
    """
    ws = find_workspace(start)
    if ws is not None:
        return ws

    # Fall back to cwd
    cwd = Path.cwd()
    return Workspace(root=cwd, config_file=cwd / "qwex.yaml")
