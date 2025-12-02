"""Configuration parsing for qwex.yaml"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel


# =============================================================================
# Layer Configs - Base + Discriminated Union
# =============================================================================


class LayerConfig(BaseModel):
    """Base layer config - only type discriminator"""

    type: str

    model_config = {"extra": "allow"}


class SSHLayerConfig(LayerConfig):
    """SSH layer configuration"""

    type: Literal["ssh"] = "ssh"
    host: str
    user: str | None = None
    key_file: str | None = None
    port: int = 22
    config: str | None = None  # path to ssh config file
    qwex_home: str = "~/.qwex"  # remote QWEX_HOME


class DockerLayerConfig(LayerConfig):
    """Docker layer configuration"""

    type: Literal["docker"] = "docker"
    image: str
    workdir: str = "/workspace"
    mounts: list[dict[str, str]] = []
    env: dict[str, str] = {}
    extra_args: list[str] = []


class SlurmLayerConfig(LayerConfig):
    """Slurm layer configuration"""

    type: Literal["slurm"] = "slurm"
    partition: str | None = None
    time: str | None = None
    gpus: int | None = None
    cpus: int | None = None
    memory: str | None = None


class SingularityLayerConfig(LayerConfig):
    """Singularity layer configuration"""

    type: Literal["singularity"] = "singularity"
    image: str


# Layer registry for dynamic creation
_LAYER_CONFIGS: dict[str, type[LayerConfig]] = {
    "ssh": SSHLayerConfig,
    "docker": DockerLayerConfig,
    "slurm": SlurmLayerConfig,
    "singularity": SingularityLayerConfig,
}


def parse_layer_config(data: dict) -> LayerConfig:
    """Parse layer config using registry"""
    layer_type = data.get("type")
    if layer_type in _LAYER_CONFIGS:
        return _LAYER_CONFIGS[layer_type].model_validate(data)
    # Fallback to generic
    return LayerConfig.model_validate(data)


# =============================================================================
# Storage Configs - Base + Discriminated Union
# =============================================================================


class StorageConfig(BaseModel):
    """Base storage config"""

    type: str

    model_config = {"extra": "allow"}


class GitDirectStorageConfig(StorageConfig):
    """Git-direct storage: push via SSH to bare repo"""

    type: Literal["git-direct"] = "git-direct"
    depends_on: str  # layer name that provides SSH access


class MountStorageConfig(StorageConfig):
    """Mount storage: direct mount (local/docker)"""

    type: Literal["mount"] = "mount"
    source: str
    path: str | None = None


class GitStorageConfig(StorageConfig):
    """Git storage: clone from remote"""

    type: Literal["git"] = "git"
    repo: str
    ref: str = "main"
    path: str | None = None
    auth: dict | None = None


class GDriveStorageConfig(StorageConfig):
    """Google Drive storage"""

    type: Literal["gdrive"] = "gdrive"
    folder_id: str
    path: str
    readonly: bool = False
    sync: str | None = None  # "on-exit", "manual"
    auth: dict | None = None


# Storage registry
_STORAGE_CONFIGS: dict[str, type[StorageConfig]] = {
    "git-direct": GitDirectStorageConfig,
    "mount": MountStorageConfig,
    "git": GitStorageConfig,
    "gdrive": GDriveStorageConfig,
}


def parse_storage_config(data: dict) -> StorageConfig:
    """Parse storage config using registry"""
    storage_type = data.get("type")
    if storage_type in _STORAGE_CONFIGS:
        return _STORAGE_CONFIGS[storage_type].model_validate(data)
    return StorageConfig.model_validate(data)


# =============================================================================
# Runner and Main Config
# =============================================================================


class RunnerConfig(BaseModel):
    """Configuration for a runner"""

    layers: list[str] = []
    storage: dict[str, str] = {}


class QwexConfig(BaseModel):
    """Full qwex.yaml configuration"""

    name: str | None = None
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

        # Parse layers with registry
        layers = {}
        for name, layer_data in data.get("layers", {}).items():
            layers[name] = parse_layer_config(layer_data)

        # Parse storage with registry
        storage = {}
        for name, storage_data in data.get("storage", {}).items():
            storage[name] = parse_storage_config(storage_data)

        return cls(
            name=data.get("name"),
            layers=layers,
            storage=storage,
            runners={
                name: RunnerConfig.model_validate(runner_data)
                for name, runner_data in data.get("runners", {}).items()
            },
        )

    def get_runner(self, name: str | None) -> RunnerConfig | None:
        """Get runner config by name, or None for default (no layers)"""
        if name is None:
            return None
        return self.runners.get(name)
