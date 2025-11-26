"""QWP Runner Base

Abstract base class for all runners.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from qwp.models import Run, JobSpec
from qwp.store import RunStore


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

    def __init__(self, store: RunStore | None = None):
        """Initialize the runner.

        Args:
            store: Run store for persistence. Creates default if not provided.
        """
        self.store = store or RunStore()

    @abstractmethod
    async def submit(self, job_spec: JobSpec, name: str | None = None) -> Run:
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
        """List all runs.

        Returns:
            List of all runs.
        """
        return list(self.store.list_runs())
