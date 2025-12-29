"""Qwex CLI Main Entry Point

Qwex - Queued Workspace-aware Execution
A task runner inspired by Ansible's extensibility, Taskfile's simplicity,
and GitHub Actions' step-based workflow.

Usage:
    qwex                           # JIT compile and run 'help' task
    qwex <task> [args...]          # JIT compile and run task
    qwex <task> -p preset          # Run with preset
    qwex -o out.sh                 # Compile to file (run 'help' by default)
    qwex -o out.sh <task>          # Compile to file
    qwex path/to/qwex.yaml         # Use specific file
    qwex -h                        # Show this help
    qwex -v                        # Show version
"""

from __future__ import annotations

from typing import Optional, List
from pathlib import Path
import subprocess
import typer

from ._version import __version__


def find_qwex_file() -> Optional[Path]:
    """Find qwex.yaml in current directory or parents."""
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        candidate = parent / "qwex.yaml"
        if candidate.exists():
            return candidate
    return None


def parse_presets(presets_str: Optional[str]) -> Optional[List[str]]:
    """Parse comma-separated preset string into list."""
    if presets_str is None:
        return None
    return [p.strip() for p in presets_str.split(",") if p.strip()]


def is_yaml_file(arg: str) -> bool:
    """Check if argument looks like a YAML file path."""
    return arg.endswith(".yaml") or arg.endswith(".yml")


typer_app = typer.Typer()


@typer_app.command()
def cli(
    version: bool = typer.Option(
        False, "-v", "--version", help="Show version and exit."
    ),
    presets: Optional[str] = typer.Option(
        None,
        "-p",
        "--preset",
        "--presets",
        help="Comma-separated list of presets to apply.",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "-o",
        "--output",
        help="Output compiled bash to file instead of executing.",
    ),
    file_path: Optional[Path] = typer.Option(
        None, "-f", "--file", help="Path to qwex.yaml file."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print compiled bash without executing."
    ),
    args: Optional[List[str]] = typer.Argument(None),
) -> None:
    """Queued Workspace-aware Execution - task runner that compiles to bash.

    Examples:
        qwex                        Run 'help' task (lists available tasks)
        qwex greet                  Run 'greet' task
        qwex greet "hello"          Run 'greet' with argument
        qwex -p qwex eval-all       Run 'eval-all' with 'qwex' preset
        qwex -o out.sh              Compile to out.sh
        qwex path/to/qwex.yaml      Use specific file
    """
    # normalize
    if version:
        typer.echo(f"qwex {__version__}")
        raise typer.Exit()

    output = output
    file_path = file_path
    dry_run = dry_run
    args_list: List[str] = list(args) if args is not None else []

    """Queued Workspace-aware Execution - task runner that compiles to bash.

    \b
    Examples:
        qwex                        Run 'help' task (lists available tasks)
        qwex greet                  Run 'greet' task
        qwex greet "hello"          Run 'greet' with argument
        qwex -p qwex eval-all       Run 'eval-all' with 'qwex' preset
        qwex -o out.sh              Compile to out.sh
        qwex path/to/qwex.yaml      Use specific yaml file
    """
    # Parse args: first arg could be a yaml file or a task name
    filepath: Optional[Path] = file_path
    task_name: str = "help"
    task_args: List[str] = []

    if args_list and filepath is None:
        first_arg = args_list[0]
        if is_yaml_file(first_arg):
            # First arg is a yaml file
            filepath = Path(first_arg)
            if not filepath.exists():
                typer.secho(
                    f"Error: File not found: {filepath}", err=True, fg=typer.colors.RED
                )
                raise typer.Exit(code=1)
            args_list = args_list[1:]

    if args_list:
        task_name = args_list[0]
        task_args = args_list[1:]

    # Find qwex.yaml if not specified
    if filepath is None:
        filepath = find_qwex_file()
        if filepath is None:
            typer.secho(
                "Error: No qwex.yaml found in current directory or parents.",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)

    try:
        # NOTE: QWL compiler has been removed. For now emit a simple stub script
        # that informs the user that compilation/execution is not implemented.
        bash = f"""#!/usr/bin/env bash
# Qwex compiled stub — QWL compiler removed.
# Source file: {filepath}
TASK_NAME="$1"
shift || true
case "$TASK_NAME" in
  help|"")
    echo "No compiler available — QWL removed. Define tasks in {filepath.name} and implement the compiler."
    exit 0
    ;;
  *)
    echo "Task execution not implemented (requested $TASK_NAME)" >&2
    exit 1
    ;;
esac
"""

        if output is not None:
            # Write to file
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(bash, encoding="utf-8")
            typer.echo(f"Wrote compiled bash to {output}")
            raise typer.Exit()
        elif dry_run:
            # Print compiled bash
            typer.echo(bash)
            raise typer.Exit()
        else:
            # Execute via bash
            cmd = ["bash", "-s", "--", task_name] + task_args
            result = subprocess.run(
                cmd,
                input=bash,
                text=True,
            )
            raise typer.Exit(code=result.returncode)

    except Exception as exc:
        typer.secho(f"Error: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)


def app(argv: Optional[List[str]] = None) -> None:
    """Entry point for the CLI.

    When called as a module or installed entrypoint this function launches the Typer app.
    The optional `argv` parameter is currently ignored (kept for backward compatibility).
    """
    # NOTE: Typer runs via Click under the hood and handles sys.exit codes for us.
    typer_app()


if __name__ == "__main__":
    app()
