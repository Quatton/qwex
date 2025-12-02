"""Docker container layer"""

from __future__ import annotations

from qwp.layers import Layer, LayerContext, ShellCommand


class DockerLayer(Layer):
    """
    Wraps commands to run inside a Docker container.

    Example:
        layer = DockerLayer(image="python:3.12")
        wrapped = layer.wrap(
            ShellCommand(command="python", args=["train.py"]),
            ctx
        )
        # Results in: docker run --rm -v /workspace:/workspace python:3.12 python train.py
    """

    def __init__(
        self,
        image: str,
        *,
        workdir: str | None = None,
        mounts: list[tuple[str, str]] | None = None,
        env: dict[str, str] | None = None,
        extra_args: list[str] | None = None,
    ):
        """
        Args:
            image: Docker image to use
            workdir: Working directory inside container (default: /workspace)
            mounts: Additional (host_path, container_path) mounts
            env: Environment variables to set
            extra_args: Extra arguments to pass to docker run
        """
        self.image = image
        self.workdir = workdir or "/workspace"
        self.mounts = mounts or []
        self.env = env or {}
        self.extra_args = extra_args or []

    def wrap(self, inner: ShellCommand, ctx: LayerContext) -> ShellCommand:
        """Wrap command to run inside Docker container"""
        args = [
            "run",
            "--rm",  # auto-remove container
            "-i",  # interactive (for stdin)
        ]

        # Mount workspace
        args.extend(["-v", f"{ctx.workspace_root}:{self.workdir}"])

        # Mount run directory for logs
        args.extend(["-v", f"{ctx.run_dir}:/qwex/runs"])

        # Set working directory
        args.extend(["-w", self.workdir])

        # Add environment variables
        for key, value in {**self.env, **inner.env}.items():
            args.extend(["-e", f"{key}={value}"])

        # Add custom mounts
        for host_path, container_path in self.mounts:
            args.extend(["-v", f"{host_path}:{container_path}"])

        # Add extra args
        args.extend(self.extra_args)

        # Add image
        args.append(self.image)

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
        return f"DockerLayer({self.image})"
