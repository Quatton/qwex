"""Qwex CLI Main Entry Point"""

from __future__ import annotations

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from qwp import JobSpec, LocalRunner, Run, RunStatus, RunStore, Workspace

app = typer.Typer(
    name="qwex",
    help="Queued Workspace-aware Execution",
    no_args_is_help=True,
)
console = Console()


def get_workspace() -> Workspace:
    """Discover and return the current workspace."""
    return Workspace.discover()


def get_runner(workspace: Workspace | None = None) -> LocalRunner:
    """Get a local runner instance."""
    ws = workspace or get_workspace()
    return LocalRunner(workspace=ws)


def format_status(status: RunStatus) -> Text:
    """Format run status with color."""
    colors = {
        RunStatus.PENDING: "yellow",
        RunStatus.RUNNING: "blue",
        RunStatus.SUCCEEDED: "green",
        RunStatus.FAILED: "red",
        RunStatus.CANCELLED: "orange3",
    }
    return Text(status.value, style=colors.get(status, "white"))


def format_run(run: Run, verbose: bool = False) -> Panel:
    """Format a run for display."""
    lines = [
        f"[bold]ID:[/bold] {run.id}",
        f"[bold]Status:[/bold] {format_status(run.status)}",
        f"[bold]Command:[/bold] {run.job_spec.command_string()}",
    ]

    if run.name:
        lines.insert(1, f"[bold]Name:[/bold] {run.name}")

    if run.created_at:
        lines.append(
            f"[bold]Created:[/bold] {run.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )

    if run.started_at:
        lines.append(
            f"[bold]Started:[/bold] {run.started_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )

    if run.finished_at:
        lines.append(
            f"[bold]Finished:[/bold] {run.finished_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )

    if run.duration_seconds() is not None:
        lines.append(f"[bold]Duration:[/bold] {run.duration_seconds():.2f}s")

    if run.exit_code is not None:
        lines.append(f"[bold]Exit Code:[/bold] {run.exit_code}")

    if run.error:
        lines.append(f"[bold red]Error:[/bold red] {run.error}")

    if verbose and run.pid:
        lines.append(f"[bold]PID:[/bold] {run.pid}")

    return Panel("\n".join(lines), title=f"Run {run.id}", border_style="blue")


@app.command()
def run(
    command: str = typer.Argument(..., help="Command to run"),
    args: list[str] = typer.Argument(default=None, help="Command arguments"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Name for the run"),
    detach: bool = typer.Option(
        False, "--detach", "-d", help="Detach after starting (don't follow logs)"
    ),
    no_save: bool = typer.Option(
        False,
        "--no-save",
        help="Do not persist run state (delete run folder after completion)",
    ),
    env: list[str] = typer.Option(
        [], "--env", "-e", help="Environment variables (KEY=VALUE)"
    ),
) -> None:
    """Run a command locally.

    Examples:
        qwex run python train.py
        qwex run python train.py --epochs 10 --lr 0.001
        qwex run --name "experiment-1" python train.py
        qwex run --detach python long_running.py
    """
    # Parse environment variables
    env_dict = {}
    for e in env:
        if "=" in e:
            key, value = e.split("=", 1)
            env_dict[key] = value
        else:
            console.print(f"[red]Invalid env format: {e}. Use KEY=VALUE[/red]")
            raise typer.Exit(1)

    # Create job spec
    job_spec = JobSpec(
        command=command,
        args=args or [],
        env=env_dict,
    )

    runner = get_runner()

    async def do_run():
        run_obj = await runner.submit(job_spec, name=name, no_save=no_save)
        console.print(f"[green]✓[/green] Run [bold]{run_obj.id}[/bold] started")
        console.print(f"  Command: {job_spec.command_string()}")

        if detach:
            console.print(
                f"\n[dim]Detached. Use 'qwex attach {run_obj.id}' to follow logs.[/dim]"
            )
            if no_save:
                console.print(
                    "[dim]Note: --no-save was used; run state will be removed after completion.[/dim]"
                )
            return

        console.print("\n[dim]Following logs (Ctrl+C to detach)...[/dim]\n")

        try:
            async for line in runner.logs(run_obj.id, follow=True):
                console.print(line)
        except KeyboardInterrupt:
            console.print("\n[yellow]Detached.[/yellow] Run continues in background.")
            console.print(f"  Use 'qwex attach {run_obj.id}' to reattach")
            console.print(f"  Use 'qwex cancel {run_obj.id}' to stop")
            return

        # Show final status (may not exist if --no-save was used)
        try:
            final_run = await runner.get_run(run_obj.id)
            console.print()
            console.print(format_run(final_run))
        except Exception:
            # Run was deleted (--no-save)
            if no_save:
                console.print(
                    "\n[dim]Run completed and state removed (--no-save).[/dim]"
                )
            else:
                raise

    asyncio.run(do_run())


@app.command()
def attach(
    run_id: str = typer.Argument(..., help="Run ID to attach to"),
) -> None:
    """Attach to a running run and follow its logs.

    Press Ctrl+C to detach without stopping the run.
    """
    runner = get_runner()

    async def do_attach():
        try:
            run_obj = await runner.get_run(run_id)
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

        if run_obj.status.is_terminal():
            console.print(f"Run [bold]{run_id}[/bold] is already finished.")
            console.print(format_run(run_obj))

            # Show logs anyway
            console.print("\n[dim]Logs:[/dim]\n")
            async for line in runner.logs(run_id, follow=False):
                console.print(line)
            return

        console.print(f"[green]✓[/green] Attached to run [bold]{run_id}[/bold]")
        console.print(f"  Command: {run_obj.job_spec.command_string()}")
        console.print("\n[dim]Following logs (Ctrl+C to detach)...[/dim]\n")

        try:
            async for line in runner.logs(run_id, follow=True):
                console.print(line)
        except KeyboardInterrupt:
            console.print("\n[yellow]Detached.[/yellow]")
            return

        # Show final status
        final_run = await runner.get_run(run_id)
        console.print()
        console.print(format_run(final_run))

    asyncio.run(do_attach())


@app.command()
def cancel(
    run_id: str = typer.Argument(..., help="Run ID to cancel"),
    force: bool = typer.Option(False, "--force", "-f", help="Force kill (SIGKILL)"),
) -> None:
    """Cancel a running run.

    Sends SIGTERM by default, SIGKILL with --force.
    """
    runner = get_runner()

    async def do_cancel():
        try:
            run_obj = await runner.cancel(run_id)
            console.print(f"[green]✓[/green] Run [bold]{run_id}[/bold] cancelled")
            console.print(format_run(run_obj))
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    asyncio.run(do_cancel())


@app.command()
def status(
    run_id: str = typer.Argument(..., help="Run ID to check"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show more details"),
) -> None:
    """Show status of a run."""
    runner = get_runner()

    async def do_status():
        try:
            run_obj = await runner.get_run(run_id)
            console.print(format_run(run_obj, verbose=verbose))
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    asyncio.run(do_status())


@app.command("list")
def list_runs(
    all_runs: bool = typer.Option(
        False, "--all", "-a", help="Show all runs (including finished)"
    ),
) -> None:
    """List runs."""
    runner = get_runner()

    async def do_list():
        runs = await runner.list_runs()

        if not all_runs:
            runs = [r for r in runs if not r.status.is_terminal()]

        if not runs:
            if all_runs:
                console.print("[dim]No runs found.[/dim]")
            else:
                console.print(
                    "[dim]No active runs. Use --all to show finished runs.[/dim]"
                )
            return

        # Sort by created_at, newest first
        runs.sort(key=lambda r: r.created_at, reverse=True)

        for run_obj in runs:
            status_text = format_status(run_obj.status)
            name_part = f" ({run_obj.name})" if run_obj.name else ""
            console.print(
                f"[bold]{run_obj.id}[/bold]{name_part} - {status_text} - {run_obj.job_spec.command_string()}"
            )

    asyncio.run(do_list())


@app.command()
def logs(
    run_id: str = typer.Argument(..., help="Run ID"),
    follow: bool = typer.Option(
        False, "--follow", "-f", help="Follow logs in real-time"
    ),
    stderr: bool = typer.Option(
        False, "--stderr", help="Show stderr instead of stdout"
    ),
) -> None:
    """Show logs for a run."""
    runner = get_runner()
    store = runner.store

    async def do_logs():
        try:
            await runner.get_run(run_id)
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

        log_path = store.stderr_path(run_id) if stderr else store.stdout_path(run_id)

        if not log_path.exists():
            console.print("[dim]No logs found.[/dim]")
            return

        try:
            async for line in runner.logs(run_id, follow=follow):
                console.print(line)
        except KeyboardInterrupt:
            pass

    asyncio.run(do_logs())


@app.command()
def clean(
    all_runs: bool = typer.Option(
        False, "--all", "-a", help="Delete all runs (not just finished)"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Don't prompt for confirmation"
    ),
) -> None:
    """Clean up finished runs."""
    workspace = get_workspace()
    store = RunStore(workspace=workspace)

    runs = list(store.list_runs())
    if not all_runs:
        runs = [r for r in runs if r.status.is_terminal()]

    if not runs:
        console.print("[dim]No runs to clean.[/dim]")
        return

    console.print(f"Will delete {len(runs)} run(s):")
    for run_obj in runs:
        console.print(f"  - {run_obj.id} ({run_obj.status.value})")

    if not force:
        confirm = typer.confirm("Continue?")
        if not confirm:
            raise typer.Abort()

    for run_obj in runs:
        store.delete(run_obj.id)
        console.print(f"[red]✗[/red] Deleted {run_obj.id}")

    console.print(f"[green]✓[/green] Cleaned {len(runs)} run(s)")


@app.command()
def init() -> None:
    """Initialize a new qwex workspace.

    Creates an empty qwex.yaml in the current directory.
    """
    try:
        workspace = Workspace.init()
        console.print("[green]✓[/green] Created qwex.yaml")
        console.print(f"  Workspace root: {workspace.root}")
    except FileExistsError:
        console.print("[yellow]qwex.yaml already exists in this directory.[/yellow]")
        raise typer.Exit(1)


@app.command()
def info() -> None:
    """Show workspace information."""
    workspace = get_workspace()

    if workspace.is_explicit:
        console.print("[green]✓[/green] Explicit workspace (qwex.yaml found)")
        console.print(f"  Config: {workspace.config_path}")
    else:
        console.print("[yellow]![/yellow] Implicit workspace (no qwex.yaml found)")

    console.print(f"  Root: {workspace.root}")
    console.print(f"  Runs: {workspace.runs_dir}")


if __name__ == "__main__":
    app()
