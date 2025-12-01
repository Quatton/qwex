"""Qwex CLI Main Entry Point"""

from __future__ import annotations


import typer
from rich.console import Console

app = typer.Typer(
    name="qwex",
    help="Queued Workspace-aware Execution",
    no_args_is_help=True,
)
console = Console()


if __name__ == "__main__":
    app()
