"""Qwex CLI Main Entry Point"""

from __future__ import annotations

import os
import signal
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Prompt

from qwp.models import Run, RunStatus
from qwp.workspace import Workspace, find_workspace, find_workspace_or_cwd
from qwp.config import QwexConfig
from qwp.layers import Layer, LayerContext, ShellCommand
from qwp.layers.docker import DockerLayer

app = typer.Typer(
    name="qwex",
    help="Queued Workspace-aware Execution",
    no_args_is_help=True,
)
console = Console()


def get_workspace() -> Workspace:
    """Get current workspace, finding qwex.yaml or falling back to cwd"""
    ws = find_workspace()
    if ws is None:
        # Fall back to cwd with no config
        return find_workspace_or_cwd()
    return ws


@app.command()
def run(
    command: list[str] = typer.Argument(
        ..., help="Command to run (use -- to separate from qwex args)"
    ),
    runner: Optional[str] = typer.Option(
        None, "-r", "--runner", help="Runner to use (from qwex.yaml)"
    ),
) -> None:
    """Run a command and track its execution."""
    if not command:
        console.print("[red]Error:[/red] No command provided")
        raise typer.Exit(1)

    ws = get_workspace()
    runs_dir = ws.runs_dir

    # Load config and resolve runner
    config = QwexConfig.load(ws.config_file)
    runner_config = config.get_runner(runner)

    # Build layer chain
    layers: list[Layer] = []
    if runner_config:
        for layer_name in runner_config.layers:
            layer_config = config.layers.get(layer_name)
            if layer_config is None:
                console.print(f"[red]Error:[/red] Layer '{layer_name}' not found")
                raise typer.Exit(1)

            if layer_config.type == "docker":
                if not layer_config.image:
                    console.print(
                        f"[red]Error:[/red] Docker layer '{layer_name}' missing image"
                    )
                    raise typer.Exit(1)
                layers.append(DockerLayer(image=layer_config.image))
            else:
                console.print(
                    f"[yellow]Warning:[/yellow] Layer type '{layer_config.type}' not implemented yet"
                )

    # Create run
    run_obj = Run(
        command=command[0],
        args=command[1:],
        cwd=str(Path.cwd()),
    )
    run_obj.save(runs_dir)

    console.print(f"[dim]Workspace:[/dim] {ws.root}")
    console.print(f"[dim]Run ID:[/dim] {run_obj.id}")
    if layers:
        layer_names = " → ".join(layer.name for layer in layers)
        console.print(f"[dim]Layers:[/dim] {layer_names}")

    # Build the actual command to execute
    shell_cmd = ShellCommand(command=command[0], args=command[1:])

    # Apply layers (inner to outer)
    ctx = LayerContext(
        workspace_root=str(ws.root),
        run_id=run_obj.id,
        run_dir=str(runs_dir / run_obj.id),
    )
    for layer in reversed(layers):
        shell_cmd = layer.wrap(shell_cmd, ctx)

    final_command = shell_cmd.to_list()

    # Start the process
    run_obj.status = RunStatus.RUNNING
    run_obj.started_at = datetime.now(timezone.utc)

    # Ensure log file directory exists
    log_file = runs_dir / run_obj.id / "output.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Open log file for writing
    with open(log_file, "w") as log_f:
        try:
            process = subprocess.Popen(
                final_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,  # line buffered
            )
            run_obj.pid = process.pid
            run_obj.save(runs_dir)

            # Handle Ctrl-C
            detached = False

            def handle_sigint(signum, frame):
                nonlocal detached
                if detached:
                    # Second Ctrl-C during prompt = cancel
                    return

                console.print()  # newline after ^C

                # Show prompt
                try:
                    choice = Prompt.ask(
                        "What do you want to do?",
                        choices=["detach", "cancel"],
                        default="detach",
                    )
                except (KeyboardInterrupt, EOFError):
                    # Ctrl-C during prompt = cancel
                    choice = "cancel"

                if choice == "detach":
                    detached = True
                    console.print(
                        "[yellow]Detached.[/yellow] Process continues in background."
                    )
                    console.print(f"  [dim]Reattach:[/dim] qwex logs {run_obj.id}")
                    console.print(f"  [dim]Cancel:[/dim]   qwex cancel {run_obj.id}")
                    run_obj.status = RunStatus.DETACHED
                    run_obj.save(runs_dir)
                    raise SystemExit(0)
                else:
                    console.print("[red]Cancelling...[/red]")
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    run_obj.status = RunStatus.CANCELLED
                    run_obj.finished_at = datetime.now(timezone.utc)
                    run_obj.save(runs_dir)
                    raise SystemExit(1)

            original_handler = signal.signal(signal.SIGINT, handle_sigint)

            # Stream output to both console and log file
            try:
                assert process.stdout is not None
                for line in process.stdout:
                    if not detached:
                        console.print(line, end="")
                    log_f.write(line)
                    log_f.flush()

                process.wait()
            finally:
                signal.signal(signal.SIGINT, original_handler)

            run_obj.exit_code = process.returncode
            run_obj.finished_at = datetime.now(timezone.utc)

            if process.returncode == 0:
                run_obj.status = RunStatus.SUCCEEDED
                console.print(f"\n[green]✓[/green] Run {run_obj.id} succeeded")
            else:
                run_obj.status = RunStatus.FAILED
                console.print(
                    f"\n[red]✗[/red] Run {run_obj.id} failed (exit code {process.returncode})"
                )

        except Exception as e:
            run_obj.status = RunStatus.FAILED
            run_obj.error = str(e)
            run_obj.finished_at = datetime.now(timezone.utc)
            console.print(f"[red]Error:[/red] {e}")

    run_obj.save(runs_dir)


@app.command()
def logs(
    run_id: Optional[str] = typer.Argument(
        None, help="Run ID (defaults to latest run)"
    ),
    follow: bool = typer.Option(False, "-f", "--follow", help="Follow log output"),
) -> None:
    """View logs for a run."""
    runs_dir = get_workspace().runs_dir

    if run_id is None:
        # Get latest run
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

    log_file = runs_dir / run_id / "output.log"

    if not log_file.exists():
        console.print(f"[yellow]No logs found for run {run_id}[/yellow]")
        raise typer.Exit(1)

    if follow and run_obj.status == RunStatus.DETACHED:
        # Tail the log file
        console.print(f"[dim]Following logs for run {run_id}...[/dim]")
        console.print("[dim]Press Ctrl-C to stop following[/dim]\n")

        import time

        with open(log_file, "r") as f:
            # Print existing content
            console.print(f.read(), end="")

            # Follow new content
            try:
                while True:
                    line = f.readline()
                    if line:
                        console.print(line, end="")
                    else:
                        # Check if process is still running
                        run_obj = Run.load_by_id(runs_dir, run_id)
                        if run_obj.is_terminal:
                            console.print(f"\n[dim]Run {run_id} finished[/dim]")
                            break
                        time.sleep(0.1)
            except KeyboardInterrupt:
                console.print("\n[dim]Stopped following[/dim]")
    else:
        # Just print the log
        console.print(log_file.read_text())


@app.command()
def cancel(
    run_id: str = typer.Argument(..., help="Run ID to cancel"),
) -> None:
    """Cancel a running or detached run."""
    runs_dir = get_workspace().runs_dir

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
        # Update status anyway
        run_obj.status = RunStatus.CANCELLED
        run_obj.finished_at = datetime.now(timezone.utc)
        run_obj.save(runs_dir)
    except PermissionError:
        console.print(f"[red]Permission denied to kill process {run_obj.pid}[/red]")
        raise typer.Exit(1)


@app.command("list")
def list_runs() -> None:
    """List all runs."""
    runs_dir = get_workspace().runs_dir
    runs = Run.list_runs(runs_dir)

    if not runs:
        console.print("[yellow]No runs found[/yellow]")
        return

    from rich.table import Table

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

    for run in runs[:10]:  # Show last 10
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


if __name__ == "__main__":
    app()
