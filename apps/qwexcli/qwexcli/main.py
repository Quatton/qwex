"""Qwex CLI Main Entry Point"""

from __future__ import annotations

from typing import Optional

import typer

from .commands.utils import setup_logging
from .commands.run import run_command
from .commands.logs import logs_command
from .commands.cancel import cancel_command
from .commands.list import list_command

app = typer.Typer(
    name="qwex",
    help="Queued Workspace-aware Execution",
    no_args_is_help=True,
)


@app.command()
def run(
    command: list[str] = typer.Argument(
        ..., help="Command to run (use -- to separate from qwex args)"
    ),
    runner: Optional[str] = typer.Option(
        None, "-r", "--runner", help="Runner to use (from qwex.yaml)"
    ),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Verbose output"),
) -> None:
    """Run a command and track its execution."""
    setup_logging(verbose)
    run_command(command, runner, verbose)


@app.command()
def logs(
    run_id: Optional[str] = typer.Argument(
        None, help="Run ID (defaults to latest run)"
    ),
    follow: bool = typer.Option(False, "-f", "--follow", help="Follow log output"),
) -> None:
    """View logs for a run."""
    logs_command(run_id, follow)


@app.command()
def cancel(
    run_id: str = typer.Argument(..., help="Run ID to cancel"),
) -> None:
    """Cancel a running or detached run."""
    cancel_command(run_id)


@app.command("list")
def list_runs() -> None:
    """List all runs."""
    list_command()


if __name__ == "__main__":
    app()
