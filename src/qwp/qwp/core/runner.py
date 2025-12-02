"""Runner - executes commands with worktree isolation"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from qwp.core.home import QwexHome
from qwp.models import Run, RunStatus


def get_current_commit(repo_path: Path) -> str | None:
    """Get current HEAD commit hash"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def get_workspace_name(workspace_root: Path) -> str:
    """Get workspace name from directory name or qwex.yaml"""
    # TODO: read from qwex.yaml if 'name' field exists
    return workspace_root.name


def _create_worktree(
    repo_path: Path,
    target_path: Path,
    commit: str,
) -> bool:
    """Create a detached worktree at target_path from commit."""
    target_path.parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ["git", "worktree", "add", "--detach", str(target_path), commit],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _remove_worktree(repo_path: Path, target_path: Path) -> bool:
    """Remove a worktree."""
    result = subprocess.run(
        ["git", "worktree", "remove", "--force", str(target_path)],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


class LocalRunner:
    """Runs commands locally with optional worktree isolation"""

    def __init__(
        self,
        qwex_home: QwexHome,
        workspace_root: Path,
        workspace_name: str | None = None,
        use_worktree: bool = True,
    ):
        self.qwex_home = qwex_home
        self.workspace_root = workspace_root
        self.workspace_name = workspace_name or get_workspace_name(workspace_root)
        self.use_worktree = use_worktree

    def run(
        self,
        run_obj: Run,
        on_output: Callable[[str], None] | None = None,
    ) -> Run:
        """Execute a run.

        Args:
            run_obj: Run object with command/args
            on_output: Optional callback for each line of output

        Returns:
            Updated Run object
        """
        self.qwex_home.ensure_dirs()
        runs_dir = self.qwex_home.runs

        # Get commit for reproducibility
        commit = get_current_commit(self.workspace_root)
        run_obj.commit = commit
        run_obj.workspace_name = self.workspace_name

        # Determine working directory
        if self.use_worktree and commit:
            # Create worktree for isolated execution
            space_dir = self.qwex_home.space_dir(run_obj.id)
            if not _create_worktree(self.workspace_root, space_dir, commit):
                run_obj.status = RunStatus.FAILED
                run_obj.error = "Failed to create worktree"
                run_obj.save(runs_dir)
                return run_obj
            work_dir = space_dir
        else:
            # Run directly in workspace
            work_dir = self.workspace_root

        # Update status
        run_obj.append_status(runs_dir, RunStatus.RUNNING)
        run_obj.started_at = datetime.now(timezone.utc)
        run_obj.save(runs_dir)

        # Prepare log file
        log_file = run_obj.stdout_log_path(runs_dir)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # Execute command
        cmd = [run_obj.command, *run_obj.args]

        try:
            with open(log_file, "w") as log_f:
                process = subprocess.Popen(
                    cmd,
                    cwd=work_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                run_obj.pid = process.pid
                run_obj.save(runs_dir)

                assert process.stdout is not None
                for line in process.stdout:
                    log_f.write(line)
                    log_f.flush()
                    if on_output:
                        on_output(line)

                process.wait()
                run_obj.exit_code = process.returncode

        except Exception as e:
            run_obj.error = str(e)
            run_obj.exit_code = -1

        # Update final status
        run_obj.finished_at = datetime.now(timezone.utc)
        if run_obj.exit_code == 0:
            run_obj.append_status(runs_dir, RunStatus.SUCCEEDED)
        else:
            run_obj.append_status(runs_dir, RunStatus.FAILED)

        run_obj.save(runs_dir)

        # Cleanup worktree
        if self.use_worktree and commit:
            space_dir = self.qwex_home.space_dir(run_obj.id)
            _remove_worktree(self.workspace_root, space_dir)

        return run_obj
