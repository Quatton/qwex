"""Run command - execute a command with tracking"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer

from qwp.core import (
    LocalRunner,
    QwexConfig,
)
from qwp.layers import Layer, create_layer
from qwp.models import Run, RunStatus

from .utils import console, get_workspace, get_workspace_name
from .run_layers import run_with_layers

log = logging.getLogger(__name__)


def run_command(
    command: list[str],
    runner: Optional[str] = None,
    verbose: bool = False,
) -> None:
    """Run a command and track its execution."""
    if not command:
        console.print("[red]Error:[/red] No command provided")
        raise typer.Exit(1)

    ws = get_workspace()
    config = QwexConfig.load(ws.config_file)
    workspace_name = get_workspace_name(ws, config)
    runner_config = config.get_runner(runner)

    # Build layer chain
    layers: list[Layer] = []
    if runner_config:
        for layer_name in runner_config.layers:
            layer_config = config.layers.get(layer_name)
            if layer_config is None:
                console.print(f"[red]Error:[/red] Layer '{layer_name}' not found")
                raise typer.Exit(1)

            try:
                layers.append(create_layer(layer_config))
            except ValueError as e:
                console.print(f"[red]Error:[/red] {e}")
                raise typer.Exit(1)

    # Create run object
    run_obj = Run(
        command=command[0],
        args=command[1:],
        cwd=str(Path.cwd()),
    )

    console.print(f"[dim]Workspace:[/dim] {ws.root}")
    console.print(f"[dim]Run ID:[/dim] {run_obj.id}")

    if not layers:
        # Local execution with worktree isolation
        _run_local(ws, run_obj, config, workspace_name, verbose)
    else:
        # Remote/layered execution
        layer_names = " → ".join(layer.name for layer in layers)
        console.print(f"[dim]Layers:[/dim] {layer_names}")
        run_with_layers(ws, run_obj, layers, workspace_name, config, runner, verbose)


def _run_local(
    ws, run_obj: Run, config: QwexConfig, workspace_name: str, verbose: bool
) -> None:
    """Run locally with worktree isolation using LocalRunner."""
    # Use config to resolve QWEX_HOME
    qwex_home = config.resolve_qwex_home(workspace_name)

    # Ensure symlink exists
    qwex_home.ensure_workspace_symlink(ws.root, workspace_name)

    local_runner = LocalRunner(
        qwex_home=qwex_home,
        workspace_root=ws.root,
        workspace_name=workspace_name,
        use_worktree=config.settings.worktree,
    )

    if verbose:
        console.print(f"[dim]QWEX_HOME:[/dim] {qwex_home.root}")
        console.print(
            f"[dim]Worktree:[/dim] {qwex_home.space_dir(run_obj.id, workspace_name)}"
        )

    # Run with output callback
    def on_output(line: str) -> None:
        console.print(line, end="")

    result = local_runner.run(run_obj, on_output=on_output)

    if result.status == RunStatus.SUCCEEDED:
        console.print(f"\n[green]✓[/green] Run {result.id} succeeded")
    else:
        console.print(
            f"\n[red]✗[/red] Run {result.id} failed (exit code {result.exit_code})"
        )
        if result.error:
            console.print(f"[red]Error:[/red] {result.error}")
