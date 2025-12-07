"""Configuration management for qwexcli."""

from pathlib import Path
from typing import Dict, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QwexConfig(BaseModel):
    """Main qwex configuration."""

    model_config = ConfigDict(validate_assignment=True)

    version: int = Field(default=1, description="Config version")
    defaults: Dict[str, Any] = Field(
        default_factory=lambda: {"runner": "base"},
        description="Default runtime configuration (e.g., default runner)",
    )
    runners: Dict[str, Any] = Field(
        default_factory=lambda: {"base": {"plugins": ["base"]}},
        description="Named runner configurations and their plugins",
    )
    name: str = Field(
        default_factory=lambda: Path.cwd().name, description="Project name"
    )

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: int) -> int:
        if v != 1:
            raise ValueError("version must be 1")
        return v


def load_config(config_path: Path) -> QwexConfig:
    """Load configuration from YAML file.

    Note: Loaded config has Pydantic defaults filled in for missing fields.
    """
    import yaml

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    data = {}

    with open(config_path, "r") as f:
        data = yaml.safe_load(f)

    return QwexConfig(**(data))


def save_config(config: QwexConfig, config_path: Path) -> None:
    """Save configuration to YAML file."""
    import yaml

    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w") as f:
        yaml.dump(
            config.model_dump(exclude_unset=True),
            f,
            default_flow_style=False,
            sort_keys=False,
        )


def get_config_path(cwd: Path | None = None) -> Path:
    """Get .qwex/config.yaml path relative to cwd (default: current dir)."""
    base = cwd or Path.cwd()
    return base / ".qwex" / "config.yaml"


def load_project_config() -> QwexConfig:
    """Load the project configuration."""
    return load_config(get_config_path())
