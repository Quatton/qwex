"""QWP Workspace

Workspace discovery and configuration management.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


CONFIG_FILENAME = "qwex.yaml"
QWEX_DIR = ".qwex"
DEFAULT_IMAGE = "ghcr.io/astral-sh/uv:0.9.13-python3.12-bookworm-slim"


class WorkspaceConfig(BaseModel):
    """Configuration from qwex.yaml.

    Currently minimal - can be extended with:
    - defaultRunner
    - env variables
    - artifact patterns
    - etc.
    """

    workspace_dir: str = Field(
        default=".",
        alias="workspaceDir",
        description="Workspace root directory, relative to config file or absolute",
    )

    default_image: str = Field(
        default=DEFAULT_IMAGE,
        alias="defaultImage",
        description="Default container image for containerized runs",
    )

    # Future extensions
    # default_runner: str = Field(default="local", alias="defaultRunner")
    # env: dict[str, str] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class Workspace:
    """Represents a qwex workspace.

    A workspace is a directory containing:
    - Optional qwex.yaml config file
    - .qwex/ directory for runs, logs, etc.

    Discovery:
    - Search upward from cwd for qwex.yaml
    - If found, workspace root = config location + workspaceDir
    - If not found, workspace root = cwd (implicit workspace)
    """

    def __init__(
        self,
        root: Path,
        config_path: Path | None = None,
        config: WorkspaceConfig | None = None,
    ):
        """Initialize a workspace.

        Args:
            root: Resolved workspace root directory.
            config_path: Path to qwex.yaml (None if implicit workspace).
            config: Parsed configuration (defaults used if None).
        """
        self.root = root.resolve()
        self.config_path = config_path.resolve() if config_path else None
        self.config = config or WorkspaceConfig()

    @classmethod
    def discover(cls, start_path: Path | str | None = None) -> Workspace:
        """Discover workspace by searching upward for qwex.yaml.

        Args:
            start_path: Starting directory for search. Defaults to cwd.

        Returns:
            Workspace instance (explicit if config found, implicit otherwise).
        """
        start = Path(start_path) if start_path else Path.cwd()
        start = start.resolve()

        # Search upward for qwex.yaml
        config_path = cls._find_config(start)

        if config_path:
            # Explicit workspace - load config
            config = cls._load_config(config_path)
            root = cls._resolve_workspace_dir(config_path.parent, config.workspace_dir)
            return cls(root=root, config_path=config_path, config=config)
        else:
            # Implicit workspace - use start directory
            return cls(root=start, config_path=None, config=WorkspaceConfig())

    @classmethod
    def _find_config(cls, start: Path) -> Path | None:
        """Search upward for qwex.yaml, returning the bottom-most (closest to start).

        Args:
            start: Starting directory.

        Returns:
            Path to qwex.yaml or None if not found.
        """
        current = start
        found: Path | None = None

        # Walk up to filesystem root
        while True:
            config_path = current / CONFIG_FILENAME
            if config_path.is_file():
                found = config_path  # Keep searching upward, but remember this one

            parent = current.parent
            if parent == current:
                # Reached filesystem root
                break
            current = parent

        return found

    @classmethod
    def _load_config(cls, config_path: Path) -> WorkspaceConfig:
        """Load and parse qwex.yaml.

        Args:
            config_path: Path to config file.

        Returns:
            Parsed WorkspaceConfig.
        """
        content = config_path.read_text()
        if not content.strip():
            # Empty file - use defaults
            return WorkspaceConfig()

        data = yaml.safe_load(content)
        if data is None:
            # YAML parsed to None (empty or only comments)
            return WorkspaceConfig()

        return WorkspaceConfig.model_validate(data)

    @classmethod
    def _resolve_workspace_dir(cls, config_dir: Path, workspace_dir: str) -> Path:
        """Resolve workspaceDir relative to config file location.

        Args:
            config_dir: Directory containing qwex.yaml.
            workspace_dir: Value from config (relative or absolute).

        Returns:
            Resolved absolute path to workspace root.
        """
        ws_path = Path(workspace_dir)
        if ws_path.is_absolute():
            return ws_path.resolve()
        return (config_dir / ws_path).resolve()

    @property
    def qwex_dir(self) -> Path:
        """Get the .qwex directory path."""
        return self.root / QWEX_DIR

    @property
    def runs_dir(self) -> Path:
        """Get the .qwex/runs directory path."""
        return self.qwex_dir / "runs"

    @property
    def is_explicit(self) -> bool:
        """Check if this is an explicit workspace (has qwex.yaml)."""
        return self.config_path is not None

    def ensure_dirs(self) -> None:
        """Create workspace directories if they don't exist."""
        self.qwex_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def init(cls, path: Path | str | None = None) -> Workspace:
        """Initialize a new workspace by creating qwex.yaml.

        Args:
            path: Directory to create qwex.yaml in. Defaults to cwd.

        Returns:
            The newly created Workspace.

        Raises:
            FileExistsError: If qwex.yaml already exists.
        """
        target_dir = Path(path) if path else Path.cwd()
        target_dir = target_dir.resolve()
        config_path = target_dir / CONFIG_FILENAME

        if config_path.exists():
            raise FileExistsError(f"{CONFIG_FILENAME} already exists at {config_path}")

        # Create empty config file
        config_path.write_text("")

        return cls(root=target_dir, config_path=config_path, config=WorkspaceConfig())

    def __repr__(self) -> str:
        explicit = "explicit" if self.is_explicit else "implicit"
        return f"Workspace({self.root}, {explicit})"
