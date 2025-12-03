"""SSH remote execution layer"""

from __future__ import annotations

import logging
import shlex
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from qwp.core.script import build_run_script
from qwp.layers import Layer, LayerContext, ShellCommand, layer

log = logging.getLogger(__name__)


class SSHLayerConfig(BaseModel):
    type: Literal["ssh"] = "ssh"
    host: str
    user: str | None = None
    key_file: str | None = None
    port: int = 22
    config: str | None = None
    workdir: str | None = None
    cwd: str | None = None
    qwex_home: str = "~/.qwex"
    extra_args: list[str] = []

    def get_workdir(self) -> str | None:
        return self.workdir or self.cwd

    def get_config_path(self) -> str | None:
        return str(Path(self.config).expanduser()) if self.config else None

    def get_key_file_path(self) -> str | None:
        return str(Path(self.key_file).expanduser()) if self.key_file else None


@layer
class SSHLayer(Layer):
    """Wraps commands to run on a remote host via SSH"""

    def __init__(self, config: SSHLayerConfig):
        self.config = config

    def wrap(self, inner: ShellCommand, ctx: LayerContext) -> ShellCommand:
        args: list[str] = self._build_ssh_args()
        target = self.get_target()
        args.append(target)

        # Build the run script using the shared script builder
        if ctx.commit:
            log.info(f"Using worktree isolation on remote (commit: {ctx.commit[:8]})")
        else:
            log.warning("No commit available, running without worktree isolation")

        script = build_run_script(
            run_id=ctx.run_id,
            workspace_name=ctx.workspace_name,
            command=inner.to_list(),
            commit=ctx.commit,
            qwex_home=self.config.qwex_home,
            stream_output=True,
        )

        # Wrap in sh -c (more portable than bash)
        args.append(f"sh -c {shlex.quote(script)}")

        return ShellCommand(command="ssh", args=args, env={})

    @property
    def name(self) -> str:
        user_part = f"{self.config.user}@" if self.config.user else ""
        return f"SSHLayer({user_part}{self.config.host})"

    def _build_ssh_args(self) -> list[str]:
        args: list[str] = []
        if config_path := self.config.get_config_path():
            args.extend(["-F", config_path])
        if key_file := self.config.get_key_file_path():
            args.extend(["-i", key_file])
        if self.config.port != 22:
            args.extend(["-p", str(self.config.port)])
        args.extend(self.config.extra_args)
        return args

    def get_target(self) -> str:
        return (
            f"{self.config.user}@{self.config.host}"
            if self.config.user
            else self.config.host
        )
