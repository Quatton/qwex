from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from qwexcli.lib.errors import QwexError


class AlreadyInitializedError(QwexError):
    """Raised when trying to initialize an already initialized project."""

    def __init__(self) -> None:
        super().__init__("qwex is already initialized in this directory", exit_code=1)


class ProjectRootNotFoundError(QwexError):
    """Raised when no `.qwex` directory is found in any parent up to the FS root."""

    def __init__(self) -> None:
        super().__init__(
            "no .qwex directory found in any parent directories", exit_code=2
        )


def check_already_initialized(config_path: Path) -> None:
    """Raise AlreadyInitializedError if config exists at `config_path`."""
    if config_path.exists():
        raise AlreadyInitializedError()


def _default_qwex_yaml(project_name: str) -> dict[str, Any]:
    return {
        "name": project_name,
        "tasks": {
            "run": {
                "args": {"command": ""},
                "steps": [
                    {
                        "name": "Echo command",
                        "uses": "std/echo",
                        "with": {"message": "Running command: {{ args.command }}"},
                    },
                    {
                        "name": "Run command as is",
                        "uses": "std/bash",
                        "with": {"command": "{{ args.command }}"},
                    },
                    {
                        "name": "Show that run_id has first_class support",
                        "uses": "std/echo",
                        "with": {"message": "Run ID: {{ run_id }}"},
                    },
                ],
            }
        },
    }


def create_qwex_yaml_file(qwex_yaml_path: Path, name: Optional[str] = None) -> Path:
    """Create `qwex.yaml` at the explicit path and return it."""
    import yaml

    qwex_yaml_path.parent.mkdir(parents=True, exist_ok=True)

    project_name = name or qwex_yaml_path.parent.name
    data = _default_qwex_yaml(project_name)

    with open(qwex_yaml_path, "w") as f:
        yaml.safe_dump(data, f, sort_keys=False)
    return qwex_yaml_path


# Match .qwex/ or .qwex at start of line or after /
_QWEX_GITIGNORE_RE = re.compile(r"(^|/)\.qwex/?$", re.MULTILINE)


def ensure_root_gitignore_ignores_qwex(root: Path) -> Path:
    """Ensure `<root>/.gitignore` ignores `.qwex/` and return the gitignore path."""
    gitignore_path = root / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(".qwex/\n")
        return gitignore_path

    content = gitignore_path.read_text()
    if _QWEX_GITIGNORE_RE.search(content) is None:
        if not content.endswith("\n"):
            content += "\n"
        content += ".qwex/\n"
        gitignore_path.write_text(content)
    return gitignore_path


def scaffold(root: Path, name: Optional[str] = None) -> Path:
    """Scaffold the qwex project structure. Returns created qwex.yaml path."""
    qwex_yaml = root / "qwex.yaml"
    out = create_qwex_yaml_file(qwex_yaml_path=qwex_yaml, name=name)
    ensure_root_gitignore_ignores_qwex(root)
    return out


def find_project_root(start: Optional[Path] = None) -> Path:
    """Search upwards from `start` (or cwd) for a directory containing `qwex.yaml`.

    If found, returns the directory that contains `qwex.yaml`.
    If no `qwex.yaml` is found before reaching the filesystem root, raise
    `ProjectRootNotFoundError` to avoid accidentally returning the FS root.
    """
    cur = start or Path.cwd()
    cur = cur.resolve()

    for p in [cur] + list(cur.parents):
        if (p / "qwex.yaml").exists():
            return p

    # Reached FS root without finding project marker — treat as error
    raise ProjectRootNotFoundError()
