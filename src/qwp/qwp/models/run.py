"""Run model"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field
from uuid_extensions import uuid7str

from .status import RunStatus, StatusEntry


class Run(BaseModel):
    """Represents a running or completed job."""

    id: str = Field(default_factory=uuid7str)
    status: RunStatus = RunStatus.PENDING
    command: str
    args: list[str] = []
    cwd: str = "."
    env: dict[str, str] = {}

    # Git info for reproducibility
    commit: str | None = None
    workspace_name: str | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None

    exit_code: int | None = None
    error: str | None = None
    pid: int | None = None  # for detached processes

    def save(self, runs_dir: Path) -> Path:
        """Save run to runs/<id>/run.json"""
        run_dir = runs_dir / self.id
        run_dir.mkdir(parents=True, exist_ok=True)
        run_file = run_dir / "run.json"
        run_file.write_text(self.model_dump_json(indent=2))
        return run_file

    def append_status(self, runs_dir: Path, status: RunStatus) -> None:
        """Append status entry to runs/<id>/statuses.jsonl"""
        run_dir = runs_dir / self.id
        run_dir.mkdir(parents=True, exist_ok=True)
        statuses_file = run_dir / "statuses.jsonl"
        entry = StatusEntry(status=status)
        with open(statuses_file, "a") as f:
            f.write(entry.to_jsonl() + "\n")
        self.status = status

    def stdout_log_path(self, runs_dir: Path) -> Path:
        """Path to stdout.log"""
        return runs_dir / self.id / "stdout.log"

    @classmethod
    def load(cls, run_dir: Path) -> "Run":
        """Load run from directory"""
        run_file = run_dir / "run.json"
        return cls.model_validate_json(run_file.read_text())

    @classmethod
    def load_by_id(cls, runs_dir: Path, run_id: str) -> "Run":
        """Load run by ID"""
        return cls.load(runs_dir / run_id)

    @classmethod
    def list_runs(cls, runs_dir: Path) -> list["Run"]:
        """List all runs, sorted by creation time (newest first)"""
        runs = []
        if runs_dir.exists():
            for run_dir in runs_dir.iterdir():
                if run_dir.is_dir() and (run_dir / "run.json").exists():
                    try:
                        runs.append(cls.load(run_dir))
                    except Exception:
                        pass  # skip corrupted runs
        return sorted(runs, key=lambda r: r.created_at, reverse=True)

    @property
    def log_file(self) -> Path:
        """Path to stdout/stderr log file (legacy, use stdout_log_path instead)"""
        return Path(self.cwd) / ".qwex" / "runs" / self.id / "output.log"

    @property
    def is_terminal(self) -> bool:
        """Whether the run has finished (success, failed, or cancelled)"""
        return self.status in (
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        )
