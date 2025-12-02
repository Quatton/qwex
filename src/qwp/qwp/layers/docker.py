"""Docker container layer"""

from __future__ import annotations

from pydantic import BaseModel

from qwp.layers import Layer, LayerContext, ShellCommand, register_layer


class MountConfig(BaseModel):
    """Configuration for a volume mount"""

    host: str
    container: str


class DockerLayerConfig(BaseModel):
    """Configuration for Docker layer"""

    type: str = "docker"  # discriminator
    image: str
    workdir: str = "/workspace"
    mounts: list[MountConfig] = []
    env: dict[str, str] = {}
    extra_args: list[str] = []


@register_layer("docker")
class DockerLayer(Layer):
    """
    Wraps commands to run inside a Docker container.

    Example:
        config = DockerLayerConfig(image="python:3.12")
        layer = DockerLayer(config)
        wrapped = layer.wrap(
            ShellCommand(command="python", args=["train.py"]),
            ctx
        )
        # Results in: docker run --rm -v /workspace:/workspace python:3.12 python train.py
    """

    def __init__(self, config: DockerLayerConfig):
        """Initialize from DockerLayerConfig"""
        self.config = config

    def wrap(self, inner: ShellCommand, ctx: LayerContext) -> ShellCommand:
        """Wrap command to run inside Docker container"""
        args = [
            "run",
            "--rm",  # auto-remove container
            "-i",  # interactive (for stdin)
        ]

        # Mount workspace
        args.extend(["-v", f"{ctx.workspace_root}:{self.config.workdir}"])

        # Mount run directory for logs
        args.extend(["-v", f"{ctx.run_dir}:/qwex/runs"])

        # Set working directory
        args.extend(["-w", self.config.workdir])

        # Add environment variables
        for key, value in {**self.config.env, **inner.env}.items():
            args.extend(["-e", f"{key}={value}"])

        # Add custom mounts
        for mount in self.config.mounts:
            args.extend(["-v", f"{mount.host}:{mount.container}"])

        # Add extra args
        args.extend(self.config.extra_args)

        # Add image
        args.append(self.config.image)

        # Add the inner command
        args.append(inner.command)
        args.extend(inner.args)

        return ShellCommand(
            command="docker",
            args=args,
            env={},  # env is passed to docker, not to shell
        )

    @property
    def name(self) -> str:
        return f"DockerLayer({self.config.image})"
