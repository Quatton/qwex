"""Docker container layer"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from qwp.layers import Layer, LayerContext, ShellCommand, layer


class MountConfig(BaseModel):
    host: str
    container: str


class DockerLayerConfig(BaseModel):
    type: Literal["docker"] = "docker"
    image: str
    workdir: str = "/workspace"
    mounts: list[MountConfig] = []
    env: dict[str, str] = {}
    extra_args: list[str] = []


@layer
class DockerLayer(Layer):
    """Wraps commands to run inside a Docker container"""

    def __init__(self, config: DockerLayerConfig):
        self.config = config

    def wrap(self, inner: ShellCommand, ctx: LayerContext) -> ShellCommand:
        args = ["run", "--rm", "-i"]
        args.extend(["-v", f"{ctx.workspace_root}:{self.config.workdir}"])
        args.extend(["-v", f"{ctx.run_dir}:/qwex/runs"])
        args.extend(["-w", self.config.workdir])

        for key, value in {**self.config.env, **inner.env}.items():
            args.extend(["-e", f"{key}={value}"])

        for mount in self.config.mounts:
            args.extend(["-v", f"{mount.host}:{mount.container}"])

        args.extend(self.config.extra_args)
        args.append(self.config.image)
        args.append(inner.command)
        args.extend(inner.args)

        return ShellCommand(command="docker", args=args, env={})

    @property
    def name(self) -> str:
        return f"DockerLayer({self.config.image})"
