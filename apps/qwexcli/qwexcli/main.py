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

import click

from ._version import __version__
from qwl.ast.parser import Parser
from qwl.compiler.compiler import Compiler
from qwl.compiler.renderer import Renderer


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


@click.command(
    context_settings={
        "ignore_unknown_options": True,
        "allow_extra_args": True,
        "allow_interspersed_args": False,
    }
)
@click.option("-v", "--version", is_flag=True, help="Show version and exit.")
@click.option("-h", "--help", "show_help", is_flag=True, help="Show this help and exit.")
@click.option(
    "-p", "--preset", "--presets",
    "presets",
    help="Comma-separated list of presets to apply.",
)
@click.option(
    "-o", "--output",
    type=click.Path(path_type=Path),
    help="Output compiled bash to file instead of executing.",
)
@click.option(
    "-f", "--file",
    "file_path",
    type=click.Path(exists=True, path_type=Path),
    help="Path to qwex.yaml file.",
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def cli(
    ctx: click.Context,
    version: bool,
    show_help: bool,
    presets: Optional[str],
    output: Optional[Path],
    file_path: Optional[Path],
    args: tuple,
) -> None:
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
    if version:
        click.echo(f"qwex {__version__}")
        raise SystemExit(0)

    if show_help:
        click.echo(ctx.get_help())
        raise SystemExit(0)

    # Parse args: first arg could be a yaml file or a task name
    args_list = list(args)
    filepath: Optional[Path] = file_path
    task_name: str = "help"
    task_args: List[str] = []

    if args_list and filepath is None:
        first_arg = args_list[0]
        if is_yaml_file(first_arg):
            # First arg is a yaml file
            filepath = Path(first_arg)
            if not filepath.exists():
                click.echo(f"Error: File not found: {filepath}", err=True)
                raise SystemExit(1)
            args_list = args_list[1:]

    if args_list:
        task_name = args_list[0]
        task_args = args_list[1:]

    # Find qwex.yaml if not specified
    if filepath is None:
        filepath = find_qwex_file()
        if filepath is None:
            click.echo("Error: No qwex.yaml found in current directory or parents.", err=True)
            raise SystemExit(1)

    try:
        # Parse and compile
        module = Parser().parse_file(str(filepath))
        base_dir = filepath.parent
        compiler = Compiler(base_dir=base_dir)
        preset_list = parse_presets(presets)
        script = compiler.compile(module, presets=preset_list)
        bash = Renderer().render(script)

        if output is not None:
            # Write to file
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(bash, encoding="utf-8")
            click.echo(f"Wrote compiled bash to {output}")
        else:
            # Execute via bash
            cmd = ["bash", "-s", "--", task_name] + task_args
            result = subprocess.run(
                cmd,
                input=bash,
                text=True,
            )
            raise SystemExit(result.returncode)

    except SystemExit:
        raise
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        raise SystemExit(1)


def app():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    app()
