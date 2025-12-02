"""SSH remote execution layer"""

from __future__ import annotations

import logging
import shlex
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

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
        args: list[str] = []

        if config_path := self.config.get_config_path():
            args.extend(["-F", config_path])

        if key_file := self.config.get_key_file_path():
            args.extend(["-i", key_file])

        if self.config.port != 22:
            args.extend(["-p", str(self.config.port)])

        args.extend(self.config.extra_args)
        # Don't use -t (tty) for non-interactive batch commands
        # It can cause issues with output streaming and git operations

        target = self.get_target()
        args.append(target)

        # If we have a commit, use the worktree script for isolated execution
        if ctx.commit and ctx.workspace_name:
            log.info(f"Using worktree isolation on remote (commit: {ctx.commit[:8]})")
            remote_cmd = self.build_remote_runner_script(
                run_id=ctx.run_id,
                commit=ctx.commit,
                workspace_name=ctx.workspace_name,
                command=inner.command,
                args=inner.args,
            )
            # Wrap the script in bash -c
            args.append(f"bash -c {shlex.quote(remote_cmd)}")
        else:
            # Fallback: just run in workdir (no worktree isolation)
            workdir = self.config.get_workdir()
            remote_cmd = (
                f"cd {workdir} && {inner.to_string()}" if workdir else inner.to_string()
            )
            log.warning("No commit available, running without worktree isolation")
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
git worktree add --detach {space_path} {commit} 2>/dev/null
cd {space_path}
# Use tee to stream output to both console and log file
{cmd_str} 2>&1 | tee {run_path}/stdout.log
EXIT_CODE=${{PIPESTATUS[0]}}
if [ $EXIT_CODE -eq 0 ]; then
    echo '{{"status": "succeeded", "ts": "'$(date -u +%Y-%m-%dT%H:%M:%S+00:00)'"}}' >> {run_path}/statuses.jsonl
else
    echo '{{"status": "failed", "ts": "'$(date -u +%Y-%m-%dT%H:%M:%S+00:00)'"}}' >> {run_path}/statuses.jsonl
fi
cd /
git -C {repo_path} worktree remove --force {space_path} 2>/dev/null || rm -rf {space_path}
exit $EXIT_CODE
""".strip()
