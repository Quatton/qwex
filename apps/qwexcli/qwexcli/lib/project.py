from pathlib import Path
from typing import Optional

from apps.qwexcli.qwexcli.lib.config import QwexConfig, save_config
from qwexcli.lib.errors import QwexError


class AlreadyInitializedError(QwexError):
    """Raised when trying to initialize an already initialized project."""

    def __init__(self) -> None:
        super().__init__("qwex is already initialized in this directory", exit_code=1)


def check_already_initialized(config_path: Path) -> None:
    """Raise AlreadyInitializedError if config exists at `config_path`."""
    if config_path.exists():
        raise AlreadyInitializedError()


def create_config_file(config_path: Path, name: Optional[str] = None) -> Path:
    """Create .qwex/config.yaml at the explicit `config_path` and return it."""
    # Ensure parent exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    config = QwexConfig(name=name or config_path.parent.parent.name)
    save_config(config, config_path)
    return config_path


def scaffold(config_path: Path, name: Optional[str] = None) -> Path:
    """Scaffold the qwex project structure. Returns created config path."""
    return create_config_file(config_path=config_path, name=name)


def find_project_root(start: Optional[Path] = None) -> Path:
    """Search upwards from `start` (or cwd) for a directory containing `.qwex`.

    If found, returns the directory that contains `.qwex`. If not found,
    returns the `start` directory (or cwd) as a sensible default.
    """
    cur = start or Path.cwd()
    cur = cur.resolve()

    for p in [cur] + list(cur.parents):
        if (p / ".qwex").exists():
            return p

    return cur
