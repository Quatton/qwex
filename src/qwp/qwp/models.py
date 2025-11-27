"""QWP Data Models

Core models for the Qwex Protocol: Run, RunStatus, JobSpec.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from uuid_extensions import uuid7
from pydantic import BaseModel, Field


def generate_run_id() -> str:
    """Generate a time-sortable run ID using UUIDv7."""
    return str(uuid7())


class RunStatus(str, Enum):
    """Run lifecycle states.

    Simplified state machine for MVP:
        PENDING (submitted + queued + initializing)
          ↓
        RUNNING (actively executing)
          ↓
        SUCCEEDED | FAILED | CANCELLED
    """

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def is_terminal(self) -> bool:
        """Check if this status is a terminal state."""
        return self in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED)


class JobSpec(BaseModel):
    """Job specification - the template/definition of work.

    Defines what to execute: command, environment, working directory.
    """

    command: str = Field(..., description="The command to execute")
    args: list[str] = Field(default_factory=list, description="Command arguments")
    env: dict[str, str] = Field(
        default_factory=dict, description="Environment variables"
    )
    working_dir: str | None = Field(
        default=None, description="Working directory for execution"
    )

    def full_command(self) -> list[str]:
        """Get the full command as a list for subprocess."""
        return [self.command, *self.args]

    def command_string(self) -> str:
        """Get the full command as a string for display."""
        import shlex

        return shlex.join(self.full_command())


class Run(BaseModel):
    """Run - a specific execution instance of a Job.

    Each run has a unique ID, lifecycle, logs, outputs.
    Tracks: status, timestamps, exit code, process info.
    """

    id: str = Field(
        default_factory=generate_run_id,
        description="Unique run identifier",
    )
    name: str | None = Field(default=None, description="Optional human-readable name")
    status: RunStatus = Field(
        default=RunStatus.PENDING, description="Current run status"
    )
    job_spec: JobSpec = Field(..., description="The job specification being executed")

    # Timestamps
    created_at: datetime = Field(
        default_factory=datetime.now, description="When the run was created"
    )
    started_at: datetime | None = Field(
        default=None, description="When the run started executing"
    )
    finished_at: datetime | None = Field(
        default=None, description="When the run finished"
    )

    # Execution info
    pid: int | None = Field(default=None, description="Process ID (for local runs)")
    exit_code: int | None = Field(default=None, description="Exit code (when finished)")
    error: str | None = Field(default=None, description="Error message (if failed)")

    # Metadata
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    def duration_seconds(self) -> float | None:
        """Get the run duration in seconds, if available."""
        if self.started_at is None:
            return None
        end = self.finished_at or datetime.now()
        return (end - self.started_at).total_seconds()

    def is_alive(self) -> bool:
        """Check if the run process might still be alive.

        This is a heuristic - actual process checking should be done
        by the runner or store.
        """
        return not self.status.is_terminal()

    def mark_running(self, pid: int | None = None) -> None:
        """Mark the run as running."""
        self.status = RunStatus.RUNNING
        self.started_at = datetime.now()
        if pid is not None:
            self.pid = pid

    def mark_succeeded(self, exit_code: int = 0) -> None:
        """Mark the run as succeeded."""
        self.status = RunStatus.SUCCEEDED
        self.finished_at = datetime.now()
        self.exit_code = exit_code

    def mark_failed(
        self, exit_code: int | None = None, error: str | None = None
    ) -> None:
        """Mark the run as failed."""
        self.status = RunStatus.FAILED
        self.finished_at = datetime.now()
        self.exit_code = exit_code
        self.error = error

    def mark_cancelled(self) -> None:
        """Mark the run as cancelled."""
        self.status = RunStatus.CANCELLED
        self.finished_at = datetime.now()
