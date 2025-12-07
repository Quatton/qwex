"""Init-related utilities for qwexcli."""

from pathlib import Path

from .errors import QwexError


class AlreadyInitializedError(QwexError):
    """Raised when trying to initialize an already initialized project."""

    def __init__(self) -> None:
        super().__init__("qwex is already initialized in this directory", exit_code=1)


def check_already_initialized() -> None:
    """Check if qwex is already initialized and raise error if so."""
    config_path = Path(".qwex/config.yaml")
    if config_path.exists():
        raise AlreadyInitializedError()


def get_default_config() -> str:
    """Get the default qwex configuration."""
    return """# Qwex configuration
version: "1.0"
"""


def create_config_file() -> None:
    """Create the .qwex/config.yaml file with default configuration."""
    config_path = Path(".qwex/config.yaml")
    config_path.parent.mkdir(parents=True, exist_ok=True)

    config_content = get_default_config()
    config_path.write_text(config_content)


def scaffold_project() -> None:
    """Scaffold the qwex project structure."""
    # For now, just create the config file
    # TODO: Add more scaffolding as needed (directories, templates, etc.)
    create_config_file()
