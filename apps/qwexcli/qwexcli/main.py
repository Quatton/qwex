"""Qwex CLI Main Entry Point

Qwex - Queued Workspace-aware Execution
A task runner inspired by Ansible's extensibility, Taskfile's simplicity,
and GitHub Actions' step-based workflow.

Usage:
    qwex init                  # Initialize new project
    qwex tasks                 # List available tasks
    qwex presets               # List available presets
    qwex <task>                # Run a task directly
    qwex <task> --preset auto  # Run task with preset
    qwex <task> --from step2   # Start from specific step
"""

from __future__ import annotations

from typing import Optional

import typer

from ._version import __version__


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"qwex {__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="qwex",
    help="Queued Workspace-aware Execution - task runner that compiles to bash",
    invoke_without_command=True,
    no_args_is_help=True,
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-V",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """Queued Workspace-aware Execution - task runner that compiles to bash."""
    pass


if __name__ == "__main__":
    app()
