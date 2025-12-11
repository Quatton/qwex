from pathlib import Path
from typing import Optional

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


def create_config_file(config_path: Path, name: Optional[str] = None) -> Path:
    """Create .qwex/config.yaml at the explicit `config_path` and return it."""
    from qwexcli.lib.config import (
        QwexConfig,
        ExecutorConfig,
        StorageConfig,
        save_config,
    )

    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Create default config with SSH executor and git_direct storage
    cfg = QwexConfig(
        name=name or config_path.parent.parent.name,
        executor=ExecutorConfig(
            type="ssh",
            vars={
                "HOST": "your-server",  # User must configure this
                "REPO_ORIGIN": "/path/to/your/repo.git",  # User must configure this
            },
        ),
        storage=StorageConfig(
            type="git_direct",
            vars={
                "REMOTE_URL": "ssh://user@host/path/to/repo.git",  # User must configure this
            },
        ),
    )
    save_config(cfg, config_path)
    return config_path


def create_gitignore_file(config_dir: Path) -> Path:
    """Create `.gitignore` inside the given `.qwex` config directory and return the path."""
    gitignore_path = config_dir / ".gitignore"
    gitignore_path.write_text("# Ignore internal compiled artifacts\ninternal/\n")
    return gitignore_path


def scaffold(config_path: Path, name: Optional[str] = None) -> Path:
    """Scaffold the qwex project structure. Returns created config path."""
    out = create_config_file(config_path=config_path, name=name)
    # Ensure .gitignore is present in the config dir
    create_gitignore_file(config_path.parent)
    return out


def find_project_root(start: Optional[Path] = None) -> Path:
    """Search upwards from `start` (or cwd) for a directory containing `.qwex`.

    If found, returns the directory that contains `.qwex`.
    If no `.qwex` is found before reaching the filesystem root, raise
    `ProjectRootNotFoundError` to avoid accidentally returning the FS root.
    """
    cur = start or Path.cwd()
    cur = cur.resolve()

    for p in [cur] + list(cur.parents):
        if (p / ".qwex").exists():
            return p

    # Reached FS root without finding project marker — treat as error
    raise ProjectRootNotFoundError()
