"""Qwex CLI Main Entry Point

Qwex - Queued Workspace-aware Execution
A task runner inspired by Ansible's extensibility, Taskfile's simplicity,
and GitHub Actions' step-based workflow.
"""

from __future__ import annotations

from typing import Optional
from pathlib import Path

import typer

from ._version import __version__
from qwl.ast.parser import Parser
from qwl.compiler.compiler import Compiler
from qwl.compiler.renderer import Renderer


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"qwex {__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="qwex",
    help="Queued Workspace-aware Execution - task runner that compiles to bash",
    invoke_without_command=True,
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
) -> None:
    """Queued Workspace-aware Execution - task runner that compiles to bash."""
    pass


if __name__ == "__main__":
    app()


@app.command("compile")
def compile_cmd(
    filepath: Path = typer.Argument(..., help="Path to a Qwex YAML file"),
    out: Optional[Path] = typer.Option(
        None, "--out", "-o", help="Write compiled bash to this path"
    ),
    debug: bool = typer.Option(False, "--debug", help="Raise on error for debugging"),
) -> None:
    """Compile a YAML module to bash and print or write it.

    Example:
        qwex compile playground/hello-world/qwex.yaml
        qwex compile playground/hello-world/qwex.yaml -o .qwex/_internal/compiled/noop.sh
    """
    try:
        module = Parser().parse_file(str(filepath))
        base_dir = filepath.parent
        compiler = Compiler(base_dir=base_dir)
        script = compiler.compile(module)
        bash = Renderer().render(script)

        if out is not None:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(bash, encoding="utf-8")
            typer.echo(f"Wrote compiled bash to {out}")
        else:
            typer.echo(bash)
    except Exception as exc:
        if debug:
            raise
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)
