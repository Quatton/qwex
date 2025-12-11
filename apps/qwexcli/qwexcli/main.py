"""Qwex CLI Main Entry Point"""

from __future__ import annotations

from typing import Optional, List

import json
import subprocess
import sys
from pathlib import Path

import typer

from ._version import __version__
from .lib.context import CLIContext
from .services.project import ProjectService


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
    return None


@app.command()
def init(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force reinitialization by removing existing .qwex directory",
    ),
) -> None:
    """Initialize qwex in the current directory."""
    ctx = CLIContext(force=force)
    svc = ProjectService(ctx)
    svc.init()


@app.command()
def run(
    runner: str = typer.Option(
        ..., "--runner", "-r", help="Runner name to invoke (file under .qwex/runners)"
    ),
    cmd_and_args: List[str] = typer.Argument(
        ..., help="Command and args to pass to the runner (first arg is the command)"
    ),
) -> None:
    """Locate a runner under `.qwex/runners/<runner>.py` and execute it.

    The runner is executed with the same Python interpreter. The CLI will
    translate the provided command and args into `--command` and `--args`
    parameters passed to the runner script. `--args` is JSON-encoded list.
    """
    # Ensure we have at least a command
    if len(cmd_and_args) == 0:
        typer.echo("No command provided to run", err=True)
        raise typer.Exit(code=2)

    cwd = Path.cwd()
    script = cwd / ".qwex" / "runners" / f"{runner}.py"
    if not script.exists():
        typer.echo(f"Runner not found: {script}", err=True)
        raise typer.Exit(code=3)

    command = cmd_and_args[0]
    args = cmd_and_args[1:]

    proc_cmd = [
        sys.executable,
        str(script),
        "--command",
        command,
        "--args",
        json.dumps(args),
    ]

    # Run and stream output
    try:
        rc = subprocess.run(proc_cmd)
        raise typer.Exit(code=rc.returncode)
    except FileNotFoundError:
        typer.echo("Failed to execute Python interpreter", err=True)
        raise typer.Exit(code=4)
