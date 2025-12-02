"""Status entry model"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DETACHED = "detached"  # running in background


class StatusEntry(BaseModel):
    """A single status change entry for statuses.jsonl"""

    status: RunStatus
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_jsonl(self) -> str:
        """Convert to JSON line"""
        return json.dumps({"status": self.status.value, "ts": self.ts.isoformat()})
