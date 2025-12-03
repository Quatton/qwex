"""Runner - executes commands locally using POSIX scripts"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from qwp.core.home import QwexHome
from qwp.core.script import build_run_script
from qwp.models import Run, RunStatus

log = logging.getLogger(__name__)


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


class LocalRunner:
    """Runs commands locally using POSIX script wrapper.

    Uses the same script as remote execution for consistency.
    Output is streamed via subprocess for rich formatting.
    """

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
        """Execute a run using POSIX script.

        Args:
            run_obj: Run object with command/args
            on_output: Optional callback for each line of output

        Returns:
            Updated Run object
        """
        self.qwex_home.ensure_dirs(self.workspace_name)
        runs_dir = self.qwex_home.runs(self.workspace_name)

        # Get commit for reproducibility
        commit = get_current_commit(self.workspace_root) if self.use_worktree else None
        run_obj.commit = commit
        run_obj.workspace_name = self.workspace_name

        log.debug(
            f"Starting run {run_obj.id} (commit: {commit[:8] if commit else 'none'})"
        )

        # Build the POSIX script (same as remote execution)
        script = build_run_script(
            run_id=run_obj.id,
            workspace_name=self.workspace_name,
            command=[run_obj.command, *run_obj.args],
            commit=commit,
            qwex_home=str(self.qwex_home.root),
            repo_path=str(self.workspace_root),  # Local: use workspace as repo
            stream_output=True,  # Use tee so we can capture output
        )

        log.debug(f"Running script:\n{script}")

        # Save initial state
        run_obj.started_at = datetime.now(timezone.utc)
        run_obj.save(runs_dir)

        try:
            # Execute via sh -c
            # We run from workspace_root so git operations work
            process = subprocess.Popen(
                ["sh", "-c", script],
                cwd=self.workspace_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            run_obj.pid = process.pid
            run_obj.save(runs_dir)

            # Stream output
            assert process.stdout is not None
            for line in process.stdout:
                if on_output:
                    on_output(line)

            process.wait()
            run_obj.exit_code = process.returncode

        except Exception as e:
            log.exception(f"Error during run {run_obj.id}")
            run_obj.error = str(e)
            run_obj.exit_code = -1

        # Update Run object (status already written by script)
        run_obj.finished_at = datetime.now(timezone.utc)
        if run_obj.exit_code == 0:
            run_obj.status = RunStatus.SUCCEEDED
            log.info(f"Run {run_obj.id} succeeded")
        else:
            run_obj.status = RunStatus.FAILED
            log.info(f"Run {run_obj.id} failed (exit code {run_obj.exit_code})")

        run_obj.save(runs_dir)

        return run_obj
