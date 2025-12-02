"""SSH remote execution layer"""

from __future__ import annotations

from qwp.layers import Layer, LayerContext, ShellCommand


class SSHLayer(Layer):
    """
    Wraps commands to run on a remote host via SSH.

    Example:
        layer = SSHLayer(host="remote.example.com", user="user")
        wrapped = layer.wrap(
            ShellCommand(command="python", args=["train.py"]),
            ctx
        )
        # Results in: ssh -t user@remote.example.com 'cd /workspace && python train.py'
    """

    def __init__(
        self,
        host: str,
        user: str | None = None,
        key_file: str | None = None,
        port: int = 22,
        workdir: str | None = None,
        extra_args: list[str] | None = None,
    ):
        """
        Args:
            host: Remote host to connect to
            user: SSH user (default: current user)
            key_file: Path to SSH private key file
            port: SSH port (default: 22)
            workdir: Working directory on remote host (default: /workspace)
            extra_args: Extra arguments to pass to ssh
        """
        self.host = host
        self.user = user
        self.key_file = key_file
        self.port = port
        self.workdir = workdir or "/workspace"
        self.extra_args = extra_args or []

    def wrap(self, inner: ShellCommand, ctx: LayerContext) -> ShellCommand:
        """Wrap command to run on remote host via SSH"""
        args = []

        # Add key file if specified
        if self.key_file:
            args.extend(["-i", self.key_file])

        # Add port if not default
        if self.port != 22:
            args.extend(["-p", str(self.port)])

        # Add extra args
        args.extend(self.extra_args)

        # Add -t for pseudo-terminal
        args.append("-t")

        # Build target
        target = self.host
        if self.user:
            target = f"{self.user}@{self.host}"

        args.append(target)

        # Build remote command: cd to workdir and run inner command
        remote_cmd = f"cd {self.workdir} && {inner.to_string()}"
        args.append(remote_cmd)

        return ShellCommand(
            command="ssh",
            args=args,
            env={},  # env handled in remote command if needed
        )

    @property
    def name(self) -> str:
        user_part = f"{self.user}@" if self.user else ""
        return f"SSHLayer({user_part}{self.host})"