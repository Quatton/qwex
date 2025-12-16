"""Compiler IR spec - Bash script intermediate representation."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class BashFunction:
    """A single bash function definition."""

    name: str  # e.g., "std:step"
    body: str  # rendered function body
    dependencies: List[str] = field(default_factory=list)  # e.g., ["std:once", "log:debug"]


@dataclass
class BashScript:
    """Complete bash script IR."""

    preamble: str = "#!/usr/bin/env bash\n\nset -u"
    functions: List[BashFunction] = field(default_factory=list)
    entrypoint: str = '"${@:-help}"'
