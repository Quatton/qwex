"""Init helpers for qwexcli."""

from pathlib import Path
from typing import Optional

from .config import QwexConfig, get_config_path, save_config
from .errors import QwexError


class AlreadyInitializedError(QwexError):
    """Raised when trying to initialize an already initialized project."""

    def __init__(self) -> None:
        super().__init__("qwex is already initialized in this directory", exit_code=1)


def check_already_initialized(
    cwd: Optional[Path] = None, config_path: Optional[Path] = None
) -> None:
    """Raise AlreadyInitializedError if config exists.

    If both cwd and config_path are given, config_path takes precedence.
    """
    if config_path is None:
        config_path = get_config_path(cwd)

    if config_path.exists():
        raise AlreadyInitializedError()


def create_config_file(
    cwd: Optional[Path] = None,
    config_path: Optional[Path] = None,
    name: Optional[str] = None,
) -> Path:
    """Create .qwex/config.yaml. Returns the created path."""
    cwd = cwd or Path.cwd()
    if config_path is None:
        config_path = get_config_path(cwd)

    config = QwexConfig(name=name or cwd.name)
    save_config(config, config_path)
    return config_path


def scaffold(
    cwd: Optional[Path] = None,
    config_path: Optional[Path] = None,
    name: Optional[str] = None,
) -> Path:
    """Scaffold the qwex project structure. Returns created config path."""
    return create_config_file(cwd=cwd, config_path=config_path, name=name)
