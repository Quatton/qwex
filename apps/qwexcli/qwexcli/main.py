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

import os
from pathlib import Path
from typing import Optional, List

import click
import typer
from typer.core import TyperGroup

from ._version import __version__
from .lib.project import find_project_root, ProjectRootNotFoundError, scaffold
from .lib.runner import TaskRunner
from .lib.errors import exit_with_error


# Global state for --config option
class CLIState:
    config_path: Optional[Path] = None
    project_root: Optional[Path] = None


state = CLIState()


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"qwex {__version__}")
        raise typer.Exit()


def config_callback(ctx: typer.Context, value: Optional[Path]) -> Optional[Path]:
    """Handle --config option to specify custom qwex.yaml location."""
    if value:
        if not value.exists():
            exit_with_error(f"Config file not found: {value}")
        state.config_path = value.resolve()
        state.project_root = value.parent
    return value


def get_project_root() -> Path:
    """Get project root, preferring --config path if specified."""
    if state.project_root:
        return state.project_root
    try:
        return find_project_root()
    except ProjectRootNotFoundError:
        exit_with_error(
            "Not in a qwex project (no qwex.yaml found). Use --config or run 'qwex init'"
        )
        raise  # unreachable, but keeps type checker happy


def get_runner() -> TaskRunner:
    """Get a TaskRunner with proper config path."""
    root = get_project_root()
    runner = TaskRunner(root)
    if state.config_path:
        runner.qwex_yaml_path = state.config_path
    return runner


# Custom Click group that handles unknown commands as task names
class QwexGroup(TyperGroup):
    """Custom Click group that treats unknown commands as task names."""

    def resolve_command(self, ctx: click.Context, args: list[str]) -> tuple:
        """Override to handle unknown commands as tasks."""
        # First try to resolve normally
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError as e:
            # Unknown command - check if it's a task name
            if args:
                cmd_name = args[0]
                try:
                    root = (
                        find_project_root()
                        if not state.project_root
                        else state.project_root
                    )
                    runner = TaskRunner(root)
                    if state.config_path:
                        runner.qwex_yaml_path = state.config_path
                    tasks = runner.list_tasks()
                    if cmd_name in tasks:
                        # Rewrite args to use _task command with task name
                        new_args = ["_task", cmd_name] + args[1:]
                        return super().resolve_command(ctx, new_args)
                except (ProjectRootNotFoundError, FileNotFoundError):
                    pass
            raise e

    def get_command(self, ctx: click.Context, cmd_name: str) -> Optional[click.Command]:
        """Get command, falling back to task execution."""
        return super().get_command(ctx, cmd_name)


app = typer.Typer(
    name="qwex",
    help="Queued Workspace-aware Execution - task runner that compiles to bash",
    invoke_without_command=True,
    cls=QwexGroup,
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
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        callback=config_callback,
        is_eager=True,
        help="Path to qwex.yaml config file.",
    ),
) -> None:
    """Queued Workspace-aware Execution - task runner that compiles to bash.

    Run tasks directly: qwex <task_name>
    Or use subcommands: qwex init, qwex tasks, etc.
    """
    pass


@app.command()
def init(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force reinitialization by overwriting existing qwex.yaml",
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="Project name (default: directory name)",
    ),
) -> None:
    """Initialize qwex in the current directory.

    Creates qwex.yaml with a default 'run' task and ensures .gitignore
    includes .qwex/ directory.
    """
    root = Path.cwd()
    qwex_yaml = root / "qwex.yaml"

    if qwex_yaml.exists() and not force:
        exit_with_error("qwex.yaml already exists (use --force to overwrite)")

    out = scaffold(root=root, name=name)
    typer.echo(f"Initialized qwex project: {out}")


@app.command()
def tasks() -> None:
    """List available tasks."""
    runner = get_runner()
    task_list = runner.list_tasks()

    if not task_list:
        typer.echo("No tasks defined in qwex.yaml")
        return

    typer.echo("Available tasks:")
    for t in task_list:
        typer.echo(f"  - {t}")


@app.command()
def presets() -> None:
    """List available presets (mode overlays)."""
    runner = get_runner()
    preset_list = runner.list_modes()

    if not preset_list:
        typer.echo("No presets defined in qwex.yaml")
        return

    typer.echo("Available presets:")
    for p in preset_list:
        typer.echo(f"  - {p}")


# Keep 'modes' as alias for backwards compatibility
@app.command(hidden=True)
def modes() -> None:
    """List available modes (alias for presets)."""
    presets()


@app.command(
    name="_task",
    hidden=True,
    context_settings={"allow_extra_args": True, "allow_interspersed_args": True},
)
def task_exec(
    ctx: typer.Context,
    task_name: str = typer.Argument(..., help="Name of the task to execute"),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Print the compiled bash script without executing",
    ),
    preset: Optional[str] = typer.Option(
        None,
        "--preset",
        "-p",
        help="Preset overlay to apply (e.g., 'auto', 'runbook')",
    ),
    mode: Optional[str] = typer.Option(
        None,
        "--mode",
        "-m",
        hidden=True,
        help="[Deprecated] Use --preset instead",
    ),
    from_step: Optional[str] = typer.Option(
        None,
        "--from",
        help="Start execution from this step (by id or name)",
    ),
    step: Optional[str] = typer.Option(
        None,
        "--step",
        "-s",
        help="Run only this specific step (by id or name)",
    ),
    args: Optional[List[str]] = typer.Option(
        None,
        "--arg",
        "-a",
        help="Task arguments in key=value format (can be repeated)",
    ),
) -> None:
    """Execute a task by name.

    Examples:
        qwex build
        qwex deploy --preset auto
        qwex setup --from step2
        qwex test --step unit_tests
    """
    # Handle deprecated --mode flag
    effective_preset = preset or mode
    if mode and not preset:
        typer.echo("Warning: --mode is deprecated, use --preset instead", err=True)

    runner = get_runner()

    # Parse key=value args
    cli_args: dict[str, str] = {}
    if args:
        for arg in args:
            if "=" not in arg:
                exit_with_error(f"Invalid argument format: {arg} (expected key=value)")
            key, value = arg.split("=", 1)
            cli_args[key] = value

    try:
        exit_code = runner.run_task(
            task_name,
            cli_args=cli_args,
            mode=effective_preset,
            dry_run=dry_run,
            from_step=from_step,
            only_step=step,
        )
        raise typer.Exit(exit_code)
    except ValueError as e:
        exit_with_error(str(e))
    except FileNotFoundError as e:
        exit_with_error(str(e))


@app.command(
    context_settings={"allow_extra_args": True, "allow_interspersed_args": False}
)
def run(
    ctx: typer.Context,
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Print the compiled bash script without executing",
    ),
    command: Optional[str] = typer.Argument(
        None,
        help="Command to run (passed as args.command to the 'run' task)",
    ),
) -> None:
    """Run the 'run' task with the given command.

    This is a shortcut for: qwex run --arg command="your command"

    Examples:
        qwex run python train.py
        qwex run "echo hello && echo world"
        qwex run --dry-run python main.py
    """
    runner = get_runner()

    # Combine command argument with extra args
    all_args = []
    if command:
        all_args.append(command)
    all_args.extend(ctx.args)

    full_command = " ".join(all_args) if all_args else ""

    try:
        exit_code = runner.run_task(
            "run",
            cli_args={"command": full_command},
            dry_run=dry_run,
        )
        raise typer.Exit(exit_code)
    except ValueError as e:
        exit_with_error(str(e))
    except FileNotFoundError as e:
        exit_with_error(str(e))


@app.command()
def compile(
    task_name: str = typer.Argument("run", help="Name of the task to compile"),
    preset: Optional[str] = typer.Option(
        None,
        "--preset",
        "-p",
        help="Preset overlay to apply (e.g., 'auto', 'runbook')",
    ),
    mode: Optional[str] = typer.Option(
        None,
        "--mode",
        "-m",
        hidden=True,
        help="[Deprecated] Use --preset instead",
    ),
    args: Optional[List[str]] = typer.Option(
        None,
        "--arg",
        "-a",
        help="Task arguments in key=value format",
    ),
) -> None:
    """Compile a task to bash and print it (alias for <task> --dry-run)."""
    effective_preset = preset or mode
    if mode and not preset:
        typer.echo("Warning: --mode is deprecated, use --preset instead", err=True)

    runner = get_runner()

    # Parse key=value args
    cli_args: dict[str, str] = {}
    if args:
        for arg in args:
            if "=" not in arg:
                exit_with_error(f"Invalid argument format: {arg} (expected key=value)")
            key, value = arg.split("=", 1)
            cli_args[key] = value

    try:
        runner.run_task(
            task_name, cli_args=cli_args, mode=effective_preset, dry_run=True
        )
    except ValueError as e:
        exit_with_error(str(e))
    except FileNotFoundError as e:
        exit_with_error(str(e))


# Keep 'exec' as hidden alias for backwards compatibility
@app.command(hidden=True)
def exec(
    task_name: str = typer.Argument(..., help="Name of the task to execute"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n"),
    mode: Optional[str] = typer.Option(None, "--mode", "-m"),
    args: Optional[List[str]] = typer.Option(None, "--arg", "-a"),
) -> None:
    """[Deprecated] Use 'qwex <task>' directly instead."""
    typer.echo("Note: 'qwex exec' is deprecated. Use 'qwex <task>' directly.", err=True)

    runner = get_runner()
    cli_args: dict[str, str] = {}
    if args:
        for arg in args:
            if "=" not in arg:
                exit_with_error(f"Invalid argument format: {arg} (expected key=value)")
            key, value = arg.split("=", 1)
            cli_args[key] = value

    try:
        exit_code = runner.run_task(
            task_name, cli_args=cli_args, mode=mode, dry_run=dry_run
        )
        raise typer.Exit(exit_code)
    except ValueError as e:
        exit_with_error(str(e))
    except FileNotFoundError as e:
        exit_with_error(str(e))


if __name__ == "__main__":
    app()
