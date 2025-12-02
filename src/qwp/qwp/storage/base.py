"""Base storage abstraction"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import get_args, get_origin, get_type_hints

from pydantic import BaseModel


class StorageConfig(BaseModel):
    """Base configuration for storage backends"""

    type: str

    model_config = {"extra": "allow"}


class Storage(ABC):
    """Base class for storage backends"""

    @abstractmethod
    def push(self, local_path: Path, remote_ref: str) -> None:
        pass

    @abstractmethod
    def pull(self, remote_ref: str, local_path: Path) -> None:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass


_STORAGE_REGISTRY: dict[str, tuple[type[Storage], type[StorageConfig]]] = {}


def _get_literal_value(annotation) -> str | None:
    """Extract the string value from a Literal type annotation"""
    if get_origin(annotation) is type(None):
        return None
    args = get_args(annotation)
    if args and isinstance(args[0], str):
        return args[0]
    return None


def register_storage(cls: type[Storage]) -> type[Storage]:
    """Decorator to register a storage type (infers type from config's Literal)"""
    hints = get_type_hints(cls.__init__)
    config_cls = hints.get("config")
    if not config_cls:
        raise ValueError(f"{cls} must have a typed 'config' parameter")

    type_field = config_cls.model_fields.get("type")
    if not type_field:
        raise ValueError(f"{config_cls} must have a 'type' field")

    type_value = _get_literal_value(type_field.annotation)
    if not type_value:
        raise ValueError(f"{config_cls}.type must be a Literal string")

    _STORAGE_REGISTRY[type_value] = (cls, config_cls)
    return cls


def create_storage(config: StorageConfig | dict) -> Storage:
    """Create a storage instance from configuration"""
    type_key = config.get("type") if isinstance(config, dict) else config.type
    if not type_key:
        raise ValueError("Storage config must have 'type' field")

    entry = _STORAGE_REGISTRY.get(type_key)
    if entry is None:
        raise ValueError(f"Unknown storage type: {type_key}")

    storage_cls, config_cls = entry

    if isinstance(config, dict):
        typed_config = config_cls(**config)
    elif isinstance(config, config_cls):
        typed_config = config
    else:
        typed_config = config_cls(**config.model_dump())

    return storage_cls(typed_config)
