"""QWP Docker Runner

Executes jobs in ephemeral Docker containers.
Supports detach/attach workflow with host-mount source transfer.
"""

from __future__ import annotations

import asyncio
import shlex
from typing import TYPE_CHECKING, AsyncIterator

from qwp.exceptions import RunNotAliveError
from qwp.models import JobSpec, Run, RunStatus
from qwp.runners.base import Runner
from qwp.store import RunStore

if TYPE_CHECKING:
    from qwp.workspace import Workspace


class DockerRunner(Runner):
    """Docker runner that executes jobs in ephemeral containers.

    Features:
    - Spawns Docker containers with workspace mounted as volume
    - Supports detach: container continues running after CLI exits
    - Supports attach: tail logs and wait for completion
    - Supports cancel: docker stop/kill container
    - Ephemeral: containers are removed after completion (--rm)

    Source Transfer Protocol:
    - type: "host-mount" (default) - mounts workspace root as /workspace
    """

    def __init__(
        self,
        workspace: Workspace | None = None,
        store: RunStore | None = None,
        default_image: str | None = None,
    ):
        """Initialize the Docker runner.

        Args:
            workspace: Workspace instance. If None, discovers from cwd.
            store: Run store for persistence. Creates from workspace if not provided.
            default_image: Default container image. If None, uses workspace config.
        """
        super().__init__(workspace=workspace, store=store)
        # Use provided image, or workspace config, or module default
        if default_image:
            self.default_image = default_image
        else:
            self.default_image = self.workspace.config.default_image
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    def _get_image(self, job_spec: JobSpec) -> str:
        """Get the image to use for a job.

        Args:
            job_spec: The job specification.

        Returns:
            Image name to use.
        """
        if job_spec.image:
            return job_spec.image.name
        return self.default_image

    def _build_docker_command(
        self,
        run: Run,
        job_spec: JobSpec,
        stdout_path: str,
        stderr_path: str,
        exit_code_path: str,
        runner_log_path: str,
    ) -> str:
        """Build the docker run command.

        Args:
            run: The run object.
            job_spec: The job specification.
            stdout_path: Path to stdout log file.
            stderr_path: Path to stder`r log file.
            exit_code_path: Path to exit code file.
            runner_log_path: Path to runner log file (Docker/runner messages).

        Returns:
            Shell command string to execute.
        """
        image = self._get_image(job_spec)
        workspace_root = str(self.workspace.root)
        container_workspace = "/workspace"

        # Determine working directory inside container
        if job_spec.working_dir:
            # If working_dir is absolute and starts with workspace, make it relative
            wd = job_spec.working_dir
            if wd.startswith(workspace_root):
                wd = wd[len(workspace_root) :].lstrip("/")
            container_cwd = f"{container_workspace}/{wd}" if wd else container_workspace
        else:
            container_cwd = container_workspace

        # Build docker run command parts
        # NOTE: Don't use --rm here, we need to capture logs after container exits
        docker_parts = [
            "docker",
            "run",
            "-d",  # Detached mode (we manage output ourselves)
            f"--name=qwex-{run.id}",
            f"-v={shlex.quote(workspace_root)}:{container_workspace}",
            f"-w={container_cwd}",
        ]

        # Add environment variables
        env = {
            "QWEX_RUN_ID": run.id,
            "QWEX_RUN_DIR": str(self.store.runs_path / run.id),
            **job_spec.env,
        }
        for key, value in env.items():
            docker_parts.append(f"-e={shlex.quote(f'{key}={value}')}")

        # Add image
        docker_parts.append(image)

        # Add command (quote each argument for shell safety)
        docker_parts.extend(shlex.quote(arg) for arg in job_spec.full_command())

        docker_cmd = " ".join(docker_parts)

        # Wrap in shell script that:
        # 1. Starts container and captures container ID (Docker errors go to runner.log)
        # 2. Streams logs in real-time (docker logs -f follows until container exits)
        # 3. Waits for container to finish (docker logs -f returns when container exits)
        # 4. Captures exit code and removes container
        #
        # Note: We run docker logs -f in foreground with output redirected.
        # It will exit automatically when the container exits.
        # Then we get the exit code and clean up.
        #
        # Docker/runner messages (image pull failures, container start failures, etc.)
        # are captured separately in runner.log, distinct from the command's stderr.
        wrapper = f"""
container_id=$({docker_cmd} 2>> {shlex.quote(runner_log_path)})
if [ -z "$container_id" ]; then
    echo "Failed to start container - see runner.log for details" >> {shlex.quote(runner_log_path)}
    echo "1" > {shlex.quote(exit_code_path)}
    exit 1
fi
echo "$container_id" > {shlex.quote(str(self.store._run_dir(run.id) / "container_id"))}
# Stream logs - this blocks until container exits
docker logs -f "$container_id" > {shlex.quote(stdout_path)} 2> {shlex.quote(stderr_path)}
# Get exit code after container finishes
exit_code=$(docker wait "$container_id" 2>> {shlex.quote(runner_log_path)} || docker inspect --format='{{{{.State.ExitCode}}}}' "$container_id" 2>> {shlex.quote(runner_log_path)} || echo "1")
# Clean up container
docker rm "$container_id" >> {shlex.quote(runner_log_path)} 2>&1 || true
echo "$exit_code" > {shlex.quote(exit_code_path)}
exit $exit_code
"""
        return wrapper.strip()

    async def submit(
        self, job_spec: JobSpec, name: str | None = None, no_save: bool = False
    ) -> Run:
        """Submit a job for Docker execution.

        Creates a run, spawns a Docker container with workspace mounted,
        and captures logs and exit code.

        Args:
            job_spec: The job specification to execute.
            name: Optional human-readable name for the run.
            no_save: If True, delete run directory after completion.

        Returns:
            The created Run object (status will be RUNNING).
        """
        # Create run
        run = Run(job_spec=job_spec, name=name)
        self.store.create(run)

        # File paths
        stdout_path = str(self.store.stdout_path(run.id))
        stderr_path = str(self.store.stderr_path(run.id))
        exit_code_path = str(self.store.exit_code_path(run.id))
        runner_log_path = str(self.store.runner_log_path(run.id))

        # Build docker command
        wrapper_cmd = self._build_docker_command(
            run, job_spec, stdout_path, stderr_path, exit_code_path, runner_log_path
        )

        # Set no_save flag on the run
        if no_save:
            run.no_save = True

        try:
            # Spawn wrapper process
            process = await asyncio.create_subprocess_shell(
                wrapper_cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                cwd=str(self.workspace.root),
                start_new_session=True,  # Detach from terminal
            )

            # Update run with PID (of wrapper process)
            run.mark_running(pid=process.pid)
            # Store container info in metadata
            run.metadata["runner"] = "docker"
            run.metadata["image"] = self._get_image(job_spec)
            self.store.update(run)

            # Store process reference for this session
            self._processes[run.id] = process

            # Start background task to monitor process
            asyncio.create_task(self._monitor_process(run.id, process))

        except Exception as e:
            run.mark_failed(error=str(e))
            self.store.update(run)

        return run

    async def _monitor_process(
        self,
        run_id: str,
        process: asyncio.subprocess.Process,
    ) -> None:
        """Monitor a process and update run status when it exits."""
        try:
            exit_code = await process.wait()

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

    def _get_container_id(self, run_id: str) -> str | None:
        """Get the Docker container ID for a run.

        Args:
            run_id: The run ID.

        Returns:
            Container ID or None if not found.
        """
        container_id_path = self.store._run_dir(run_id) / "container_id"
        if container_id_path.exists():
            return container_id_path.read_text().strip()
        return None

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

        Stops the Docker container.

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

        # Try to stop the container
        container_id = self._get_container_id(run_id)
        if container_id:
            # Try graceful stop first
            stop_proc = await asyncio.create_subprocess_exec(
                "docker",
                "stop",
                "-t",
                "5",
                container_id,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await stop_proc.wait()

        # Also try to kill the wrapper process
        if self.store.kill_process(run, force=False):
            await asyncio.sleep(0.5)
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
                        # Run was deleted (no_save) or otherwise unavailable
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

        Args:
            run_id: The run ID.

        Yields:
            Log lines.

        Raises:
            RunNotFoundError: If the run is not found.
        """
        async for line in self.logs(run_id, follow=True):
            yield line
