from __future__ import annotations

from pathlib import Path

import msgspec

from .node import Config


def parse_yaml_text(text: str) -> Config | None:
    """Parse a YAML string and return a `Config` instance.

    This normalizes `cmd` to always be a list of strings and ensures
    missing sections default to empty mappings.
    """

    msgspec.yaml.decode(text, type=Config)


def parse_yaml_file(path: str | Path) -> Config | None:
    """Load YAML from a file and parse it."""

    p = Path(path)
    return parse_yaml_text(p.read_text())
