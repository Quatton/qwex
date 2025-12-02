"""Layer system for wrapping commands"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from qwp.core.config import LayerConfig


class ShellCommand(BaseModel):
    """Represents a command to be executed by a shell"""

    command: str
    args: list[str] = []
    env: dict[str, str] = {}

    def to_list(self) -> list[str]:
        """Convert to list for subprocess"""
        return [self.command, *self.args]

    def to_string(self) -> str:
        """Convert to shell string"""
        import shlex

        return shlex.join(self.to_list())


class LayerContext(BaseModel):
    """Context passed to layers during wrapping"""

    workspace_root: str
    run_id: str
    run_dir: str  # .qwex/runs/<run_id>

    model_config = {"arbitrary_types_allowed": True}


class Layer(ABC):
    """Base class for execution layers that wrap commands"""

    @abstractmethod
    def wrap(self, inner: ShellCommand, ctx: LayerContext) -> ShellCommand:
        """
        Wrap the inner command.

        Args:
            inner: The command to wrap
            ctx: Context about the current run

        Returns:
            A new ShellCommand that wraps the inner command
        """
        pass

    @property
    def name(self) -> str:
        """Layer name for logging"""
        return self.__class__.__name__


# Layer registry for dynamic creation
_LAYER_REGISTRY: dict[str, tuple[type[Layer], type[BaseModel]]] = {}


def register_layer(type_name: str):
    """Decorator to register a layer type with its config class"""

    def decorator(cls: type[Layer]) -> type[Layer]:
        # Find the config class from the layer's __init__ type hints
        import inspect

        sig = inspect.signature(cls.__init__)
        config_param = sig.parameters.get("config")
        if config_param and config_param.annotation != inspect.Parameter.empty:
            config_cls = config_param.annotation
            _LAYER_REGISTRY[type_name] = (cls, config_cls)
        else:
            raise ValueError(f"Layer {cls} must have a typed 'config' parameter")
        return cls

    return decorator


def create_layer(config: "LayerConfig | dict") -> Layer:
    """Create a layer instance from configuration using registry"""
    # Handle dict input
    if isinstance(config, dict):
        type_name = config.get("type")
        if not type_name:
            raise ValueError("Layer config must have 'type' field")
    else:
        type_name = config.type

    entry = _LAYER_REGISTRY.get(type_name)
    if entry is None:
        raise ValueError(f"Unknown layer type: {type_name}")

    layer_cls, config_cls = entry

    # Convert to the proper config type if needed
    if isinstance(config, dict):
        typed_config = config_cls(**config)
    elif isinstance(config, config_cls):
        typed_config = config
    else:
        # Try to convert from generic LayerConfig
        typed_config = config_cls(**config.model_dump())

    return layer_cls(typed_config)


# Import concrete layers to trigger registration
from qwp.layers import docker, ssh  # noqa: E402, F401
