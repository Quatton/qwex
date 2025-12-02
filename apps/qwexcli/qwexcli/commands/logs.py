"""Logs command - view run logs"""

from __future__ import annotations

import time
from typing import Optional

import typer

from qwp.core import resolve_qwex_home, QwexConfig
from qwp.models import Run, RunStatus

from .utils import console, get_workspace, get_workspace_name


def logs_command(
    run_id: Optional[str] = None,
    follow: bool = False,
) -> None:
    """View logs for a run."""
    ws = get_workspace()
    config = QwexConfig.load(ws.config_file)
    workspace_name = get_workspace_name(ws, config)

    qwex_home = resolve_qwex_home(workspace_name=workspace_name)
    runs_dir = qwex_home.runs(workspace_name)

    if run_id is None:
        runs = Run.list_runs(runs_dir)
        if not runs:
            console.print("[yellow]No runs found[/yellow]")
            raise typer.Exit(1)
        run_obj = runs[0]
        run_id = run_obj.id
    else:
        try:
            run_obj = Run.load_by_id(runs_dir, run_id)
        except FileNotFoundError:
            console.print(f"[red]Run {run_id} not found[/red]")
            raise typer.Exit(1)

    log_file = runs_dir / run_id / "stdout.log"

    # Also check output.log for backward compatibility
    if not log_file.exists():
        log_file = runs_dir / run_id / "output.log"

    if not log_file.exists():
        console.print(f"[yellow]No logs found for run {run_id}[/yellow]")
        raise typer.Exit(1)

    if follow and run_obj.status == RunStatus.DETACHED:
        console.print(f"[dim]Following logs for run {run_id}...[/dim]")
        console.print("[dim]Press Ctrl-C to stop following[/dim]\n")

        with open(log_file, "r") as f:
            console.print(f.read(), end="")

            try:
                while True:
                    line = f.readline()
                    if line:
                        console.print(line, end="")
                    else:
                        run_obj = Run.load_by_id(runs_dir, run_id)
                        if run_obj.is_terminal:
                            console.print(f"\n[dim]Run {run_id} finished[/dim]")
                            break
                        time.sleep(0.1)
            except KeyboardInterrupt:
                console.print("\n[dim]Stopped following[/dim]")
    else:
        console.print(log_file.read_text())
