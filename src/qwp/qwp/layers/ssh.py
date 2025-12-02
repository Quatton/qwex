"""SSH remote execution layer"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from qwp.layers import Layer, LayerContext, ShellCommand, register_layer


class SSHLayerConfig(BaseModel):
    """Configuration for SSH layer"""

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


@register_layer
class SSHLayer(Layer):
    """Wraps commands to run on a remote host via SSH"""

    def __init__(self, config: SSHLayerConfig):
        self.config = config

    def wrap(self, inner: ShellCommand, ctx: LayerContext) -> ShellCommand:
        args: list[str] = []

        if config_path := self.config.get_config_path():
            args.extend(["-F", config_path])

        if key_file := self.config.get_key_file_path():
            args.extend(["-i", key_file])

        if self.config.port != 22:
            args.extend(["-p", str(self.config.port)])

        args.extend(self.config.extra_args)
        args.append("-t")

        target = (
            f"{self.config.user}@{self.config.host}"
            if self.config.user
            else self.config.host
        )
        args.append(target)

        workdir = self.config.get_workdir()
        remote_cmd = (
            f"cd {workdir} && {inner.to_string()}" if workdir else inner.to_string()
        )
        args.append(remote_cmd)

        return ShellCommand(command="ssh", args=args, env={})

    @property
    def name(self) -> str:
        user_part = f"{self.config.user}@" if self.config.user else ""
        return f"SSHLayer({user_part}{self.config.host})"

    def build_ssh_args(self) -> list[str]:
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

    def build_remote_runner_script(
        self,
        run_id: str,
        commit: str,
        workspace_name: str,
        command: str,
        args: list[str],
    ) -> str:
        qwex_home = self.config.qwex_home.rstrip("/")
        repo_path = f"{qwex_home}/repos/{workspace_name}.git"
        space_path = f"{qwex_home}/spaces/{run_id}"
        run_path = f"{qwex_home}/runs/{run_id}"
        cmd_str = shlex.join([command, *args])

        return f"""
set -e
mkdir -p {qwex_home}/repos {qwex_home}/spaces {qwex_home}/runs
mkdir -p {run_path}
echo '{{"status": "running", "ts": "'$(date -u +%Y-%m-%dT%H:%M:%S+00:00)'"}}' >> {run_path}/statuses.jsonl
cd {repo_path}
git worktree add --detach {space_path} {commit}
cd {space_path}
{cmd_str} > {run_path}/stdout.log 2>&1
EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo '{{"status": "succeeded", "ts": "'$(date -u +%Y-%m-%dT%H:%M:%S+00:00)'"}}' >> {run_path}/statuses.jsonl
else
    echo '{{"status": "failed", "ts": "'$(date -u +%Y-%m-%dT%H:%M:%S+00:00)'"}}' >> {run_path}/statuses.jsonl
fi
cd {repo_path}
git worktree remove --force {space_path} || true
exit $EXIT_CODE
""".strip()
