"""Init-related utilities for qwexcli."""

from .config import QwexConfig, get_config_path, save_config
from .errors import QwexError


class AlreadyInitializedError(QwexError):
    """Raised when trying to initialize an already initialized project."""

    def __init__(self) -> None:
        super().__init__("qwex is already initialized in this directory", exit_code=1)


def check_already_initialized() -> None:
    """Check if qwex is already initialized and raise error if so."""
    config_path = get_config_path()
    if config_path.exists():
        raise AlreadyInitializedError()


def create_config_file() -> None:
    """Create the .qwex/config.yaml file with default configuration."""
    from pathlib import Path

    config = QwexConfig(name=Path.cwd().name)
    config_path = get_config_path()
    save_config(config, config_path)


def scaffold_project() -> None:
    """Scaffold the qwex project structure."""
    # For now, just create the config file
    # TODO: Add more scaffolding as needed (directories, templates, etc.)
    create_config_file()
