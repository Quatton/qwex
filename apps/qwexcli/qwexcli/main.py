"""Qwex CLI Main Entry Point"""

from __future__ import annotations

import shutil
from typing import Optional, List

import typer

from ._version import __version__
from .lib.context import CLIContext
from .lib.config import load_config
from .lib.project import find_project_root, ProjectRootNotFoundError
from .lib.component import get_bundled_templates_dir
from .services.project import ProjectService
from .services.run import RunService, RunConfig


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"qwex {__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="qwex",
    help="Queued Workspace-aware Execution",
    no_args_is_help=True,
)


def _get_run_service() -> RunService:
    """Load config and create RunService."""
    try:
        project_root = find_project_root()
    except ProjectRootNotFoundError:
        typer.echo("Error: not in a qwex project (no .qwex directory found)", err=True)
        raise typer.Exit(1)

    config_path = project_root / ".qwex" / "config.yaml"
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        typer.echo(f"Error: config not found at {config_path}", err=True)
        raise typer.Exit(1)

    run_config = RunConfig(
        executor=config.executor.uses,
        executor_vars=config.executor.vars,
        storage=config.storage.uses,
        storage_vars=config.storage.vars,
        project_name=config.name,
        project_root=project_root,
    )

    return RunService(run_config)


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
    command: List[str] = typer.Argument(..., help="Command to run on remote"),
) -> None:
    """Run a command on the remote executor."""
    svc = _get_run_service()
    cmd = " ".join(command)
    exit_code = svc.run(cmd)
    raise typer.Exit(exit_code)


@app.command()
def status(
    run_id: Optional[str] = typer.Argument(None, help="Run ID (default: latest)"),
) -> None:
    """Show status of a run."""
    svc = _get_run_service()
    info = svc.status(run_id)

    if "error" in info:
        typer.echo(f"Error: {info['error']}")
        raise typer.Exit(1)

    typer.echo(f"Run: {info['run_id']}")
    typer.echo(f"Status: {info['status']}")
    typer.echo(f"Commit: {info['commit']}")
    typer.echo(f"Started: {info['started']}")
    typer.echo(f"Finished: {info['finished']}")
    typer.echo(f"Exit: {info['exit_code']}")


@app.command("list")
def list_runs() -> None:
    """List all runs."""
    svc = _get_run_service()
    runs = svc.list_runs()

    if not runs:
        typer.echo("(no runs)")
        return

    for run_id in runs:
        typer.echo(run_id)


@app.command()
def cancel(
    run_id: Optional[str] = typer.Argument(None, help="Run ID (default: latest)"),
) -> None:
    """Cancel a running job."""
    svc = _get_run_service()
    success = svc.cancel(run_id)
    if not success:
        raise typer.Exit(1)


@app.command()
def logs(
    run_id: Optional[str] = typer.Argument(None, help="Run ID (default: latest)"),
) -> None:
    """Show logs for a run."""
    svc = _get_run_service()
    stdout, stderr = svc.logs(run_id)

    if stdout:
        typer.echo(stdout, nl=False)
    if stderr:
        typer.echo(stderr, err=True, nl=False)


@app.command()
def pull(
    run_id: Optional[str] = typer.Argument(None, help="Run ID (default: latest)"),
) -> None:
    """Pull run logs to local directory."""
    svc = _get_run_service()
    try:
        path = svc.pull(run_id)
        typer.echo(f"Pulled to: {path}")
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def add(
    component: str = typer.Argument(..., help="Component path (e.g., executors/ssh)"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing"),
) -> None:
    """Copy a bundled component to project for customization.

    Example:
        qwex add executors/ssh
        qwex add storages/git_direct
    """
    try:
        project_root = find_project_root()
    except ProjectRootNotFoundError:
        typer.echo("Error: not in a qwex project (no .qwex directory found)", err=True)
        raise typer.Exit(1)

    # Normalize path
    ref = component.removesuffix(".yaml")
    bundled = get_bundled_templates_dir() / f"{ref}.yaml"

    if not bundled.exists():
        typer.echo(f"Error: bundled component '{component}' not found", err=True)
        typer.echo(f"Searched: {bundled}", err=True)
        raise typer.Exit(1)

    dest = project_root / ".qwex" / "components" / f"{ref}.yaml"

    if dest.exists() and not force:
        typer.echo(f"Error: {dest} already exists (use --force to overwrite)", err=True)
        raise typer.Exit(1)

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(bundled, dest)
    typer.echo(f"Copied to: {dest}")
