"""Configuration management for qwexcli."""

from pathlib import Path
from typing import List

from pydantic import BaseModel, Field


class QwexConfig(BaseModel):
    """Main qwex configuration."""

    version: int = Field(default=1, description="Config version")
    workspaces: List[str] = Field(
        default_factory=lambda: ["."], description="List of workspace relative paths"
    )
    name: str = Field(
        default_factory=lambda: Path.cwd().name, description="Project name"
    )

    class Config:
        """Pydantic config."""

        validate_assignment = True


def load_config(config_path: Path) -> QwexConfig:
    """Load configuration from YAML file."""
    import yaml

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        data = yaml.safe_load(f)

    return QwexConfig(**data)


def save_config(config: QwexConfig, config_path: Path) -> None:
    """Save configuration to YAML file."""
    import yaml

    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w") as f:
        yaml.dump(config.model_dump(), f, default_flow_style=False, sort_keys=False)


def get_config_path() -> Path:
    """Get the path to the qwex config file."""
    return Path(".qwex/config.yaml")


def load_project_config() -> QwexConfig:
    """Load the project configuration."""
    return load_config(get_config_path())
