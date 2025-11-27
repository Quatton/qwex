"""QWP Local Runner

Executes jobs on the local machine via subprocess.
Supports detach/attach workflow.
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, AsyncIterator

from qwp.exceptions import RunNotAliveError
from qwp.models import JobSpec, Run, RunStatus
from qwp.runners.base import Runner
from qwp.store import RunStore

if TYPE_CHECKING:
    from qwp.workspace import Workspace


class LocalRunner(Runner):
    """Local runner that executes jobs via subprocess.

    Features:
    - Spawns subprocess with stdout/stderr redirected to log files
    - Supports detach: process continues running after CLI exits
    - Supports attach: tail logs and wait for completion
    - Supports cancel: send SIGTERM/SIGKILL to process

    Note: This runner skips qwp.json manifest checking - it executes directly.
    """

    def __init__(
        self,
        workspace: Workspace | None = None,
        store: RunStore | None = None,
    ):
        """Initialize the local runner.

        Args:
            workspace: Workspace instance. If None, discovers from cwd.
            store: Run store for persistence. Creates from workspace if not provided.
        """
        super().__init__(workspace=workspace, store=store)
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    async def submit(
        self, job_spec: JobSpec, name: str | None = None, no_save: bool = False
    ) -> Run:
        """Submit a job for local execution.

        Creates a run, spawns subprocess wrapped in a shell script that
        captures the exit code to a file. This allows detached processes
        to have their exit code recovered.

        Args:
            job_spec: The job specification to execute.
            name: Optional human-readable name for the run.

        Returns:
            The created Run object (status will be RUNNING).
        """
        # Create run
        run = Run(job_spec=job_spec, name=name)
        self.store.create(run)

        # Prepare environment
        env = os.environ.copy()
        env.update(job_spec.env)
        env["QWEX_RUN_ID"] = run.id
        env["QWEX_RUN_DIR"] = str(self.store.runs_path / run.id)

        # Determine working directory
        cwd = job_spec.working_dir or str(self.workspace.root)

        # File paths
        stdout_path = self.store.stdout_path(run.id)
        stderr_path = self.store.stderr_path(run.id)
        exit_code_path = self.store.exit_code_path(run.id)

        # Build the command with shell wrapper to capture exit code
        # This ensures exit code is written even after detach
        import shlex

        cmd_str = shlex.join(job_spec.full_command())
        # Shell wrapper just captures exit code; cleanup (if no_save) happens
        # in sync_status after the run completes and status is updated.
        wrapper_cmd = f"{cmd_str}; echo $? > {shlex.quote(str(exit_code_path))}"

        # Set no_save flag on the run (persisted so detached runs get cleaned up)
        if no_save:
            run.no_save = True

        try:
            # Open log files
            stdout_file = open(stdout_path, "w")
            stderr_file = open(stderr_path, "w")

            # Spawn subprocess with shell wrapper
            process = await asyncio.create_subprocess_shell(
                wrapper_cmd,
                stdout=stdout_file,
                stderr=stderr_file,
                cwd=cwd,
                env=env,
                start_new_session=True,  # Detach from terminal
            )

            # Update run with PID
            run.mark_running(pid=process.pid)
            # persist marker whether or not we will remove later (store.create already saved)
            self.store.update(run)

            # Store process reference for this session
            self._processes[run.id] = process

            # Start background task to monitor process (for attached mode)
            asyncio.create_task(
                self._monitor_process(run.id, process, stdout_file, stderr_file)
            )

        except Exception as e:
            run.mark_failed(error=str(e))
            self.store.update(run)

        return run

    async def _monitor_process(
        self,
        run_id: str,
        process: asyncio.subprocess.Process,
        stdout_file,
        stderr_file,
    ) -> None:
        """Monitor a process and update run status when it exits."""
        try:
            exit_code = await process.wait()

            # Close log files
            stdout_file.close()
            stderr_file.close()

            # Write exit code to file (for recovery after detach)
            try:
                self.store.exit_code_path(run_id).write_text(str(exit_code))
            except Exception:
                pass

            # Update run status and handle no_save cleanup via sync_status
            try:
                run = self.store.get(run_id)
                if run.status == RunStatus.RUNNING:  # Not cancelled
                    if exit_code == 0:
                        run.mark_succeeded(exit_code)
                    else:
                        run.mark_failed(exit_code)
                    self.store.update(run)
                # sync_status will delete if no_save is set
                self.store.sync_status(run)
            except Exception:
                pass

        except Exception:
            pass  # Ignore errors in background task
        finally:
            # Remove from tracked processes
            self._processes.pop(run_id, None)

    async def get_run(self, run_id: str) -> Run:
        """Get a run by ID, syncing status with actual process state.

        Args:
            run_id: The run ID.

        Returns:
            The Run object with synced status.

        Raises:
            RunNotFoundError: If the run is not found.
        """
        run = self.store.get(run_id)
        return self.store.sync_status(run)

    async def cancel(self, run_id: str) -> Run:
        """Cancel a running run.

        Sends SIGTERM to the process, then SIGKILL if it doesn't stop.

        Args:
            run_id: The run ID to cancel.

        Returns:
            The updated Run object.

        Raises:
            RunNotFoundError: If the run is not found.
            RunNotAliveError: If the run is not running.
        """
        run = await self.get_run(run_id)

        if run.status.is_terminal():
            raise RunNotAliveError(run_id)

        # Try graceful termination first
        if self.store.kill_process(run, force=False):
            # Wait a bit for graceful shutdown
            await asyncio.sleep(0.5)

            # Check if still alive, force kill if needed
            if self.store.is_process_alive(run):
                self.store.kill_process(run, force=True)

        # Update status
        run.mark_cancelled()
        self.store.update(run)

        return run

    async def wait(self, run_id: str) -> Run:
        """Wait for a run to complete.

        Args:
            run_id: The run ID to wait for.

        Returns:
            The completed Run object.

        Raises:
            RunNotFoundError: If the run is not found.
        """
        while True:
            run = await self.get_run(run_id)
            if run.status.is_terminal():
                return run
            await asyncio.sleep(0.1)

    async def logs(self, run_id: str, follow: bool = False) -> AsyncIterator[str]:
        """Stream logs from a run.

        Reads from stdout.log file. If follow=True, continues reading
        as new content is written (like tail -f).

        Args:
            run_id: The run ID.
            follow: If True, follow logs in real-time.

        Yields:
            Log lines.

        Raises:
            RunNotFoundError: If the run is not found.
        """
        run = await self.get_run(run_id)
        stdout_path = self.store.stdout_path(run_id)

        if not stdout_path.exists():
            return

        with open(stdout_path, "r") as f:
            while True:
                line = f.readline()
                if line:
                    yield line.rstrip("\n")
                elif follow:
                    # Check if run is still going
                    try:
                        run = await self.get_run(run_id)
                        if run.status.is_terminal():
                            # Read any remaining content
                            remaining = f.read()
                            if remaining:
                                for line in remaining.splitlines():
                                    yield line
                            break
                    except Exception:
                        # Run was deleted (no_save) or otherwise unavailable;
                        # read any remaining content and exit
                        remaining = f.read()
                        if remaining:
                            for line in remaining.splitlines():
                                yield line
                        break
                    await asyncio.sleep(0.1)
                else:
                    break

    async def attach(self, run_id: str) -> AsyncIterator[str]:
        """Attach to a running run and stream its logs.

        This is a convenience method that combines logs(follow=True)
        with status checking.

        Args:
            run_id: The run ID.

        Yields:
            Log lines.

        Raises:
            RunNotFoundError: If the run is not found.
        """
        async for line in self.logs(run_id, follow=True):
            yield line
