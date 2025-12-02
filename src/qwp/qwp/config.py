"""Configuration parsing for qwex.yaml"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel


class LayerConfig(BaseModel):
    """Configuration for a layer"""

    type: str
    # Docker/Singularity fields
    image: str | None = None
    # SSH fields
    host: str | None = None
    user: str | None = None
    key_file: str | None = None
    port: int | None = None
    # Common fields
    workdir: str | None = None
    mounts: list[dict[str, str]] | None = None
    env: dict[str, str] | None = None
    extra_args: list[str] | None = None

    class Config:
        extra = "allow"  # allow additional fields


class StorageConfig(BaseModel):
    """Configuration for storage"""

    type: str
    source: str | None = None
    path: str | None = None

    class Config:
        extra = "allow"


class RunnerConfig(BaseModel):
    """Configuration for a runner"""

    layers: list[str] = []
    storage: dict[str, str] = {}


class QwexConfig(BaseModel):
    """Full qwex.yaml configuration"""

    layers: dict[str, LayerConfig] = {}
    storage: dict[str, StorageConfig] = {}
    runners: dict[str, RunnerConfig] = {}

    @classmethod
    def load(cls, path: Path) -> "QwexConfig":
        """Load config from yaml file"""
        if not path.exists():
            return cls()

        with open(path) as f:
            data = yaml.safe_load(f) or {}

        return cls.model_validate(data)

    def get_runner(self, name: str | None) -> RunnerConfig | None:
        """Get runner config by name, or None for default (no layers)"""
        if name is None:
            return None
        return self.runners.get(name)
