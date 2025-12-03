"""Cancel command - cancel a running job"""

from __future__ import annotations

import os
import signal
from datetime import datetime, timezone

import typer

from qwp.core import QwexConfig
from qwp.models import Run, RunStatus

from .utils import console, get_workspace, get_workspace_name


def cancel_command(run_id: str) -> None:
    """Cancel a running or detached run."""
    ws = get_workspace()
    config = QwexConfig.load(ws.config_file)
    workspace_name = get_workspace_name(ws, config)

    qwex_home = config.resolve_qwex_home(workspace_name)
    runs_dir = qwex_home.runs(workspace_name)

    try:
        run_obj = Run.load_by_id(runs_dir, run_id)
    except FileNotFoundError:
        console.print(f"[red]Run {run_id} not found[/red]")
        raise typer.Exit(1)

    if run_obj.is_terminal:
        console.print(
            f"[yellow]Run {run_id} already finished ({run_obj.status})[/yellow]"
        )
        raise typer.Exit(0)

    if run_obj.pid is None:
        console.print(f"[red]No PID found for run {run_id}[/red]")
        raise typer.Exit(1)

    try:
        os.kill(run_obj.pid, signal.SIGTERM)
        console.print(f"[green]Sent SIGTERM to process {run_obj.pid}[/green]")

        run_obj.status = RunStatus.CANCELLED
        run_obj.finished_at = datetime.now(timezone.utc)
        run_obj.save(runs_dir)
    except ProcessLookupError:
        console.print(
            f"[yellow]Process {run_obj.pid} not found (already exited?)[/yellow]"
        )
        run_obj.status = RunStatus.CANCELLED
        run_obj.finished_at = datetime.now(timezone.utc)
        run_obj.save(runs_dir)
    except PermissionError:
        console.print(f"[red]Permission denied to kill process {run_obj.pid}[/red]")
        raise typer.Exit(1)
