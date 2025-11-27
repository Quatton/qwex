"""QWP Run Store

Filesystem-based persistence for runs in .qwex/runs/<run_id>/.
"""

from __future__ import annotations

import json
import os
import signal
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

from qwp.exceptions import RunAlreadyExistsError, RunNotFoundError
from qwp.models import Run, RunStatus

if TYPE_CHECKING:
    from qwp.workspace import Workspace


class RunStore:
    """Filesystem-based run storage.

    Directory structure:
        <workspace>/
          .qwex/
            runs/
              <run_id>/
                run.json      # Run metadata
                stdout.log    # Standard output
                stderr.log    # Standard error
                exit_code     # Exit code file
    """

    RUN_FILE = "run.json"
    STDOUT_FILE = "stdout.log"
    STDERR_FILE = "stderr.log"
    EXIT_CODE_FILE = "exit_code"

    def __init__(self, workspace: Workspace | None = None):
        """Initialize the store.

        Args:
            workspace: Workspace instance. If None, discovers workspace from cwd.
        """
        if workspace is None:
            from qwp.workspace import Workspace

            workspace = Workspace.discover()

        self.workspace = workspace
        self.runs_path = workspace.runs_dir

    @property
    def base_path(self) -> Path:
        """Get the workspace root path (for backwards compatibility)."""
        return self.workspace.root

    def _run_dir(self, run_id: str) -> Path:
        """Get the directory for a run."""
        return self.runs_path / run_id

    def _run_file(self, run_id: str) -> Path:
        """Get the run.json path for a run."""
        return self._run_dir(run_id) / self.RUN_FILE

    def stdout_path(self, run_id: str) -> Path:
        """Get the stdout.log path for a run."""
        return self._run_dir(run_id) / self.STDOUT_FILE

    def stderr_path(self, run_id: str) -> Path:
        """Get the stderr.log path for a run."""
        return self._run_dir(run_id) / self.STDERR_FILE

    def exit_code_path(self, run_id: str) -> Path:
        """Get the exit_code file path for a run."""
        return self._run_dir(run_id) / self.EXIT_CODE_FILE

    def exists(self, run_id: str) -> bool:
        """Check if a run exists."""
        return self._run_file(run_id).exists()

    def create(self, run: Run) -> Run:
        """Create a new run.

        Args:
            run: The run to create.

        Returns:
            The created run.

        Raises:
            RunAlreadyExistsError: If the run already exists.
        """
        if self.exists(run.id):
            raise RunAlreadyExistsError(run.id)

        run_dir = self._run_dir(run.id)
        run_dir.mkdir(parents=True, exist_ok=True)

        # Create empty log files
        self.stdout_path(run.id).touch()
        self.stderr_path(run.id).touch()

        # Save run metadata
        self._save(run)
        return run

    def _save(self, run: Run) -> None:
        """Save run metadata to disk."""
        run_file = self._run_file(run.id)
        run_file.write_text(run.model_dump_json(indent=2))

    def get(self, run_id: str) -> Run:
        """Get a run by ID.

        Args:
            run_id: The run ID.

        Returns:
            The run.

        Raises:
            RunNotFoundError: If the run is not found.
        """
        run_file = self._run_file(run_id)
        if not run_file.exists():
            raise RunNotFoundError(run_id)

        data = json.loads(run_file.read_text())
        return Run.model_validate(data)

    def update(self, run: Run) -> Run:
        """Update a run.

        Args:
            run: The run to update.

        Returns:
            The updated run.

        Raises:
            RunNotFoundError: If the run is not found.
        """
        if not self.exists(run.id):
            raise RunNotFoundError(run.id)

        self._save(run)
        return run

    def delete(self, run_id: str) -> None:
        """Delete a run and its files.

        Args:
            run_id: The run ID.

        Raises:
            RunNotFoundError: If the run is not found.
        """
        if not self.exists(run_id):
            raise RunNotFoundError(run_id)

        import shutil

        shutil.rmtree(self._run_dir(run_id))

    def list_runs(self) -> Iterator[Run]:
        """List all runs.

        Yields:
            All runs in the store.
        """
        if not self.runs_path.exists():
            return

        for run_dir in self.runs_path.iterdir():
            if run_dir.is_dir():
                run_file = run_dir / self.RUN_FILE
                if run_file.exists():
                    try:
                        data = json.loads(run_file.read_text())
                        yield Run.model_validate(data)
                    except (json.JSONDecodeError, Exception):
                        # Skip corrupted runs
                        continue

    def is_process_alive(self, run: Run) -> bool:
        """Check if a run's process is still alive.

        Args:
            run: The run to check.

        Returns:
            True if the process is alive, False otherwise.
        """
        if run.pid is None:
            return False

        try:
            # Send signal 0 to check if process exists
            os.kill(run.pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    def sync_status(self, run: Run) -> Run:
        """Sync run status with actual process state.

        If the run is marked as RUNNING but the process is dead,
        check the exit_code file to determine success/failure.

        Args:
            run: The run to sync.

        Returns:
            The synced run.
        """
        if run.status == RunStatus.RUNNING and not self.is_process_alive(run):
            # Process died - check exit code file
            exit_code_file = self.exit_code_path(run.id)
            if exit_code_file.exists():
                try:
                    exit_code = int(exit_code_file.read_text().strip())
                    if exit_code == 0:
                        run.mark_succeeded(exit_code)
                    else:
                        run.mark_failed(exit_code)
                except (ValueError, IOError):
                    run.mark_failed(error="Process terminated unexpectedly")
            else:
                # No exit code file - process was killed or crashed
                run.mark_failed(error="Process terminated unexpectedly")
            self.update(run)

        return run

    def kill_process(self, run: Run, force: bool = False) -> bool:
        """Kill a run's process.

        Args:
            run: The run whose process to kill.
            force: If True, use SIGKILL. Otherwise use SIGTERM.

        Returns:
            True if signal was sent, False if process not found.
        """
        if run.pid is None:
            return False

        try:
            sig = signal.SIGKILL if force else signal.SIGTERM
            os.kill(run.pid, sig)
            return True
        except (OSError, ProcessLookupError):
            return False
