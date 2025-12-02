"""List command - list all runs"""

from __future__ import annotations

from rich.table import Table

from qwp.core import resolve_qwex_home, QwexConfig
from qwp.models import Run, RunStatus

from .utils import console, get_workspace, get_workspace_name


def list_command() -> None:
    """List all runs."""
    ws = get_workspace()
    config = QwexConfig.load(ws.config_file)
    workspace_name = get_workspace_name(ws, config)

    qwex_home = resolve_qwex_home(workspace_name=workspace_name)
    runs_dir = qwex_home.runs(workspace_name)

    runs = Run.list_runs(runs_dir)

    if not runs:
        console.print("[yellow]No runs found[/yellow]")
        return

    table = Table()
    table.add_column("ID", style="cyan")
    table.add_column("Status")
    table.add_column("Command")
    table.add_column("Created")

    status_colors = {
        RunStatus.PENDING: "yellow",
        RunStatus.RUNNING: "blue",
        RunStatus.DETACHED: "magenta",
        RunStatus.SUCCEEDED: "green",
        RunStatus.FAILED: "red",
        RunStatus.CANCELLED: "dim",
    }

    for run in runs[:10]:
        status_color = status_colors.get(run.status, "white")
        cmd = f"{run.command} {' '.join(run.args)}"
        if len(cmd) > 40:
            cmd = cmd[:37] + "..."
        table.add_row(
            run.id,
            f"[{status_color}]{run.status.value}[/{status_color}]",
            cmd,
            run.created_at.strftime("%Y-%m-%d %H:%M"),
        )

    console.print(table)
