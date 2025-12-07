"""Qwex CLI Main Entry Point"""

from __future__ import annotations

from typing import Optional

import typer

from ._version import __version__
from .commands.init import init_command


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"qwex {__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="qwex",
    help="Queued Workspace-aware Execution",
    no_args_is_help=True,
)


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-V",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """Queued Workspace-aware Execution - Run orchestration for ML workflows."""
    pass


@app.command()
def init() -> None:
    """Initialize qwex in the current directory."""
    init_command()
