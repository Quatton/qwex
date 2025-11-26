"""QWP Exceptions

Custom exceptions for the Qwex Protocol SDK.
"""

from __future__ import annotations


class QwpError(Exception):
    """Base exception for all QWP errors."""

    pass


class RunNotFoundError(QwpError):
    """Raised when a run is not found."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(f"Run not found: {run_id}")


class RunAlreadyExistsError(QwpError):
    """Raised when trying to create a run that already exists."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(f"Run already exists: {run_id}")


class RunNotAliveError(QwpError):
    """Raised when trying to interact with a run that is not alive."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(f"Run is not alive: {run_id}")


class RunStillRunningError(QwpError):
    """Raised when trying to do something that requires a finished run."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(f"Run is still running: {run_id}")
