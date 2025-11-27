"""QWP Runner Base

Abstract base class for all runners.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, AsyncIterator

from qwp.models import JobSpec, Run
from qwp.store import RunStore

if TYPE_CHECKING:
    from qwp.workspace import Workspace


class Runner(ABC):
    """Abstract base class for runners.

    A Runner is an execution engine that:
    - Submits jobs and creates runs
    - Tracks run status
    - Provides access to logs
    - Supports cancellation

    Implementations:
    - LocalRunner: Executes on local machine via subprocess
    - (Future) QwexCloudRunner: Submits to Qwex Cloud API
    """

    def __init__(
        self,
        workspace: Workspace | None = None,
        store: RunStore | None = None,
    ):
        """Initialize the runner.

        Args:
            workspace: Workspace instance. If None, discovers from cwd.
            store: Run store for persistence. Creates from workspace if not provided.
        """
        if workspace is None:
            from qwp.workspace import Workspace

            workspace = Workspace.discover()

        self.workspace = workspace
        self.store = store or RunStore(workspace=workspace)

    @abstractmethod
    async def submit(
        self, job_spec: JobSpec, name: str | None = None, no_save: bool = False
    ) -> Run:
        """Submit a job for execution.

        Args:
            job_spec: The job specification to execute.
            name: Optional human-readable name for the run.

        Returns:
            The created Run object.
        """
        pass

    @abstractmethod
    async def get_run(self, run_id: str) -> Run:
        """Get a run by ID.

        Args:
            run_id: The run ID.

        Returns:
            The Run object.

        Raises:
            RunNotFoundError: If the run is not found.
        """
        pass

    @abstractmethod
    async def cancel(self, run_id: str) -> Run:
        """Cancel a running run.

        Args:
            run_id: The run ID to cancel.

        Returns:
            The updated Run object.

        Raises:
            RunNotFoundError: If the run is not found.
        """
        pass

    @abstractmethod
    async def wait(self, run_id: str) -> Run:
        """Wait for a run to complete.

        Args:
            run_id: The run ID to wait for.

        Returns:
            The completed Run object.

        Raises:
            RunNotFoundError: If the run is not found.
        """
        pass

    @abstractmethod
    async def logs(self, run_id: str, follow: bool = False) -> AsyncIterator[str]:
        """Stream logs from a run.

        Args:
            run_id: The run ID.
            follow: If True, follow logs in real-time (like tail -f).

        Yields:
            Log lines.

        Raises:
            RunNotFoundError: If the run is not found.
        """
        pass

    async def list_runs(self) -> list[Run]:
        """List all runs, syncing status for each.

        This also triggers cleanup for no_save runs that have completed.

        Returns:
            List of all runs (excluding those deleted by cleanup).
        """
        runs = []
        for run in self.store.list_runs():
            try:
                synced = self.store.sync_status(run)
                # sync_status deletes no_save runs when terminal, so check if still exists
                if self.store.exists(synced.id):
                    runs.append(synced)
            except Exception:
                # Run may have been deleted during sync
                pass
        return runs
