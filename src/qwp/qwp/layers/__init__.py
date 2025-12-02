"""Layer system for wrapping commands"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, get_args, get_origin, get_type_hints

from pydantic import BaseModel

if TYPE_CHECKING:
    from qwp.core.config import LayerConfig


class ShellCommand(BaseModel):
    """Represents a command to be executed by a shell"""

    command: str
    args: list[str] = []
    env: dict[str, str] = {}

    def to_list(self) -> list[str]:
        return [self.command, *self.args]

    def to_string(self) -> str:
        import shlex

        return shlex.join(self.to_list())


class LayerContext(BaseModel):
    """Context passed to layers during wrapping"""

    workspace_root: str
    run_id: str
    run_dir: str

    model_config = {"arbitrary_types_allowed": True}


class Layer(ABC):
    """Base class for execution layers that wrap commands"""

    @abstractmethod
    def wrap(self, inner: ShellCommand, ctx: LayerContext) -> ShellCommand:
        pass

    @property
    def name(self) -> str:
        return self.__class__.__name__


_LAYER_REGISTRY: dict[str, tuple[type[Layer], type[BaseModel]]] = {}


def _get_literal_value(annotation) -> str | None:
    """Extract the string value from a Literal type annotation"""
    if get_origin(annotation) is type(None):
        return None
    args = get_args(annotation)
    if args and isinstance(args[0], str):
        return args[0]
    return None


def register_layer(cls: type[Layer]) -> type[Layer]:
    """Decorator to register a layer type (infers type from config's Literal)"""
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

    _LAYER_REGISTRY[type_value] = (cls, config_cls)
    return cls


def create_layer(config: "LayerConfig | dict") -> Layer:
    """Create a layer instance from configuration"""
    type_key = config.get("type") if isinstance(config, dict) else config.type
    if not type_key:
        raise ValueError("Layer config must have 'type' field")

    entry = _LAYER_REGISTRY.get(type_key)
    if entry is None:
        raise ValueError(f"Unknown layer type: {type_key}")

    layer_cls, config_cls = entry

    if isinstance(config, dict):
        typed_config = config_cls(**config)
    elif isinstance(config, config_cls):
        typed_config = config
    else:
        typed_config = config_cls(**config.model_dump())

    return layer_cls(typed_config)


from qwp.layers import docker, ssh  # noqa: E402, F401
