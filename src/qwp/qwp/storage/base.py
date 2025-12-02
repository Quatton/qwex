"""Base storage abstraction"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel


class StorageConfig(BaseModel):
    """Base configuration for storage backends"""

    type: str

    model_config = {"extra": "allow"}


class Storage(ABC):
    """Base class for storage backends.

    Storage backends handle syncing files between local and remote locations.
    Each backend implements push (upload) and pull (download) operations.
    """

    @abstractmethod
    def push(self, local_path: Path, remote_ref: str) -> None:
        """Push local files to remote storage.

        Args:
            local_path: Local path to push from
            remote_ref: Remote reference (e.g., commit hash, folder ID)
        """
        pass

    @abstractmethod
    def pull(self, remote_ref: str, local_path: Path) -> None:
        """Pull files from remote storage to local.

        Args:
            remote_ref: Remote reference to pull
            local_path: Local path to pull to
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Storage backend name for logging"""
        pass


# Storage registry for dynamic creation
_STORAGE_REGISTRY: dict[str, tuple[type[Storage], type[StorageConfig]]] = {}


def register_storage(type_name: str):
    """Decorator to register a storage type with its config class"""

    def decorator(cls: type[Storage]) -> type[Storage]:
        import inspect

        sig = inspect.signature(cls.__init__)
        config_param = sig.parameters.get("config")
        if config_param and config_param.annotation != inspect.Parameter.empty:
            config_cls = config_param.annotation
            _STORAGE_REGISTRY[type_name] = (cls, config_cls)
        else:
            raise ValueError(f"Storage {cls} must have a typed 'config' parameter")
        return cls

    return decorator


def create_storage(config: StorageConfig | dict) -> Storage:
    """Create a storage instance from configuration using registry"""
    if isinstance(config, dict):
        type_name = config.get("type")
        if not type_name:
            raise ValueError("Storage config must have 'type' field")
    else:
        type_name = config.type

    entry = _STORAGE_REGISTRY.get(type_name)
    if entry is None:
        raise ValueError(f"Unknown storage type: {type_name}")

    storage_cls, config_cls = entry

    if isinstance(config, dict):
        typed_config = config_cls(**config)
    elif isinstance(config, config_cls):
        typed_config = config
    else:
        typed_config = config_cls(**config.model_dump())

    return storage_cls(typed_config)
