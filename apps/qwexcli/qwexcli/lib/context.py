"""CLI runtime context."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CLIContext:
    """Runtime context from CLI flags/environment."""

    cwd: Path = field(default_factory=Path.cwd)
    force: bool = False
    non_interactive: bool = False
