"""Layer system for wrapping commands"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from pydantic import BaseModel

# Concrete layer implementations are imported lazily inside `create_layer`
# to avoid circular imports during package import-time.

if TYPE_CHECKING:
    from ..config import LayerConfig


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

    class Config:
        arbitrary_types_allowed = True


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


def create_layer(config: "LayerConfig") -> Layer:
    """Create a layer instance from configuration"""
    if config.type == "docker":
        if not config.image:
            raise ValueError("Docker layer requires 'image'")
        from .docker import DockerLayer

        return DockerLayer(
            image=config.image,
            workdir=config.workdir,
            mounts=[(m["host"], m["container"]) for m in (config.mounts or [])],
            env=config.env or {},
            extra_args=config.extra_args or [],
        )
    elif config.type == "ssh":
        from .ssh import SSHLayer

        return SSHLayer(config)
    else:
        raise ValueError(f"Unknown layer type: {config.type}")
