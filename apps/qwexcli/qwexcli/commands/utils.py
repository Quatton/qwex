"""Shared utilities for CLI commands"""

from __future__ import annotations

import logging

from rich.console import Console
from rich.logging import RichHandler

from qwp.core import Workspace, find_workspace, find_workspace_or_cwd, QwexConfig

console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for qwex CLI.

    Log levels:
    - Normal: Only warnings/errors shown
    - Verbose (-v): INFO level - shows worktree create/cleanup, storage sync
    - Debug (QWEX_DEBUG=1): DEBUG level - shows everything
    """
    import os as _os

    if _os.environ.get("QWEX_DEBUG"):
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING

    # Use RichHandler for pretty output
    handler = RichHandler(
        console=console,
        show_time=verbose,
        show_path=bool(_os.environ.get("QWEX_DEBUG")),
        rich_tracebacks=True,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))

    # Configure root logger for qwp
    qwp_logger = logging.getLogger("qwp")
    qwp_logger.setLevel(level)
    qwp_logger.handlers = [handler]
    qwp_logger.propagate = False

    # Configure qwexcli logger
    cli_logger = logging.getLogger("qwexcli")
    cli_logger.setLevel(level)
    cli_logger.handlers = [handler]
    cli_logger.propagate = False


def get_workspace() -> Workspace:
    """Get current workspace, finding qwex.yaml or falling back to cwd"""
    ws = find_workspace()
    if ws is None:
        return find_workspace_or_cwd()
    return ws


def get_workspace_name(ws: Workspace, config: QwexConfig) -> str:
    """Get workspace name from config or directory name"""
    return config.name or ws.root.name
