"""Run with layers - remote/layered execution"""

from __future__ import annotations

import logging
import signal
import subprocess
from datetime import datetime, timezone

from rich.prompt import Prompt

from qwp.core import Workspace, resolve_qwex_home, get_current_commit, QwexConfig
from qwp.layers import Layer, LayerContext, ShellCommand
from qwp.models import Run, RunStatus

from .utils import console

log = logging.getLogger(__name__)


def _push_code_to_remote(
    ws: Workspace,
    workspace_name: str,
    config: QwexConfig,
    runner_name: str,
) -> None:
    """Push code to remote storage if configured."""
    runner_config = config.get_runner(runner_name)
    if not runner_config or "source" not in runner_config.storage:
        return

    storage_name = runner_config.storage["source"]
    storage_config = config.storage.get(storage_name)
    if not storage_config:
        log.warning(f"Storage '{storage_name}' not found")
        return

    # For git-direct, we need to resolve the SSH host from the layer
    if storage_config.type == "git-direct":
        depends_on = getattr(storage_config, "depends_on", None)
        if depends_on:
            layer_config = config.layers.get(depends_on)
            if layer_config:
                # Get ssh_host from layer config
                ssh_host = getattr(layer_config, "host", None)
                user = getattr(layer_config, "user", None)
                if ssh_host:
                    target = f"{user}@{ssh_host}" if user else ssh_host
                    log.info(
                        f"Pushing code to {target}:~/.qwex/repos/{workspace_name}.git"
                    )
                    _git_push_direct(ws.root, target, workspace_name)
                    return

    log.debug(f"No push needed for storage type: {storage_config.type}")


def _git_push_direct(local_repo, ssh_target: str, workspace_name: str) -> bool:
    """Push code directly via git to remote bare repo."""
    import subprocess

    qwex_home = "~/.qwex"  # TODO: get from config
    repo_path = f"{qwex_home}/repos/{workspace_name}.git"

    # Ensure bare repo exists on remote
    ensure_cmd = (
        f"mkdir -p {repo_path} && cd {repo_path} && git init --bare 2>/dev/null || true"
    )
    result = subprocess.run(
        ["ssh", ssh_target, ensure_cmd],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log.warning(f"Failed to ensure bare repo: {result.stderr}")

    # Push current HEAD
    remote_url = f"{ssh_target}:{repo_path}"
    result = subprocess.run(
        ["git", "push", "--force", remote_url, "HEAD:refs/heads/main"],
        cwd=local_repo,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        log.info(f"Pushed code to {remote_url}")
        return True
    else:
        log.error(f"Failed to push: {result.stderr}")
        return False


def run_with_layers(
    ws: Workspace,
    run_obj: Run,
    layers: list[Layer],
    workspace_name: str,
    config: QwexConfig,
    runner_name: str | None,
    verbose: bool = False,
) -> None:
    """Run with layers (remote execution)."""
    qwex_home = resolve_qwex_home(workspace_name=workspace_name)
    qwex_home.ensure_workspace_symlink(ws.root, workspace_name)
    qwex_home.ensure_dirs(workspace_name)

    runs_dir = qwex_home.runs(workspace_name)
    run_obj.save(runs_dir)

    # Get current commit for worktree isolation
    commit = get_current_commit(ws.root)
    if commit:
        log.info(f"Using commit {commit[:8]} for remote execution")
        # Push code to remote before running
        if runner_name:
            _push_code_to_remote(ws, workspace_name, config, runner_name)
    else:
        log.warning("No git commit found - remote worktree isolation disabled")

    # Build the actual command to execute
    shell_cmd = ShellCommand(command=run_obj.command, args=run_obj.args)

    # Apply layers (inner to outer)
    ctx = LayerContext(
        workspace_root=str(ws.root),
        workspace_name=workspace_name,
        run_id=run_obj.id,
        run_dir=str(runs_dir / run_obj.id),
        commit=commit,
    )
    for layer in reversed(layers):
        shell_cmd = layer.wrap(shell_cmd, ctx)

    final_command = shell_cmd.to_list()

    if verbose:
        console.print(f"[dim]Command:[/dim] {' '.join(final_command)}")

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
                bufsize=1,
            )
            run_obj.pid = process.pid
            run_obj.save(runs_dir)

            # Handle Ctrl-C
            detached = False

            def handle_sigint(signum, frame):
                nonlocal detached
                if detached:
                    return

                console.print()

                try:
                    choice = Prompt.ask(
                        "What do you want to do?",
                        choices=["detach", "cancel"],
                        default="detach",
                    )
                except (KeyboardInterrupt, EOFError):
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
