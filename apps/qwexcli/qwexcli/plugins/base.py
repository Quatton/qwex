"""Simple base plugin for qwex runners."""

from __future__ import annotations

from typing import Sequence
import subprocess


def run(argv: Sequence[str]) -> int:
    if not argv:
        return 0

    completed = subprocess.run(list(argv))
    return completed.returncode


if __name__ == "__main__":
    import sys

    raise SystemExit(run(sys.argv[1:]))
