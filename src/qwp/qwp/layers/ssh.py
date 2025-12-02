"""SSH remote execution layer"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from qwp.layers import Layer, LayerContext, ShellCommand, register_layer


class SSHLayerConfig(BaseModel):
    """Configuration for SSH layer"""

    type: str = "ssh"  # discriminator
    host: str
    user: str | None = None
    key_file: str | None = None
    port: int = 22
    config: str | None = None  # SSH config file path
    workdir: str | None = None
    cwd: str | None = None  # alias for workdir
    qwex_home: str = "~/.qwex"  # remote QWEX_HOME
    extra_args: list[str] = []

    def get_workdir(self) -> str | None:
        """Get effective workdir (prefers workdir over cwd)"""
        return self.workdir or self.cwd

    def get_config_path(self) -> str | None:
        """Get expanded config path"""
        if self.config:
            return str(Path(self.config).expanduser())
        return None

    def get_key_file_path(self) -> str | None:
        """Get expanded key file path"""
        if self.key_file:
            return str(Path(self.key_file).expanduser())
        return None


@register_layer("ssh")
class SSHLayer(Layer):
    """
    Wraps commands to run on a remote host via SSH.

    Supports SSH config aliases (e.g., 'csc' from ~/.ssh/config).

    Example:
        config = SSHLayerConfig(host="csc", config="~/.ssh/config")
        layer = SSHLayer(config)
        wrapped = layer.wrap(
            ShellCommand(command="python", args=["-c", "print('hello')"]),
            ctx
        )
        # Results in: ssh -F ~/.ssh/config -t csc 'cd /workspace && python -c ...'
    """

    def __init__(self, config: SSHLayerConfig):
        """Initialize from SSHLayerConfig"""
        self.config = config

    def wrap(self, inner: ShellCommand, ctx: LayerContext) -> ShellCommand:
        """Wrap command to run on remote host via SSH"""
        args: list[str] = []

        # Add config file if specified (allows using aliases like 'csc')
        config_path = self.config.get_config_path()
        if config_path:
            args.extend(["-F", config_path])

        # Add key file if specified
        key_file = self.config.get_key_file_path()
        if key_file:
            args.extend(["-i", key_file])

        # Add port if not default
        if self.config.port != 22:
            args.extend(["-p", str(self.config.port)])

        # Add extra args
        args.extend(self.config.extra_args)

        # Add -t for pseudo-terminal
        args.append("-t")

        # Build target - use host directly (can be an alias from ssh config)
        target = self.config.host
        if self.config.user:
            target = f"{self.config.user}@{self.config.host}"

        args.append(target)

        # Build remote command
        workdir = self.config.get_workdir()
        if workdir:
            remote_cmd = f"cd {workdir} && {inner.to_string()}"
        else:
            remote_cmd = inner.to_string()

        args.append(remote_cmd)

        return ShellCommand(
            command="ssh",
            args=args,
            env={},
        )

    @property
    def name(self) -> str:
        user_part = f"{self.config.user}@" if self.config.user else ""
        return f"SSHLayer({user_part}{self.config.host})"

    def build_ssh_args(self) -> list[str]:
        """Build SSH command arguments (without target and remote command)"""
        args: list[str] = []

        config_path = self.config.get_config_path()
        if config_path:
            args.extend(["-F", config_path])

        key_file = self.config.get_key_file_path()
        if key_file:
            args.extend(["-i", key_file])

        if self.config.port != 22:
            args.extend(["-p", str(self.config.port)])

        args.extend(self.config.extra_args)

        return args

    def get_target(self) -> str:
        """Get SSH target (user@host or just host)"""
        if self.config.user:
            return f"{self.config.user}@{self.config.host}"
        return self.config.host

    def build_remote_runner_script(
        self,
        run_id: str,
        commit: str,
        workspace_name: str,
        command: str,
        args: list[str],
    ) -> str:
        """Build a shell script to run on remote with worktree isolation.

        This script:
        1. Creates worktree from the pushed commit
        2. Runs the command
        3. Writes logs to $QWEX_HOME/runs/<run-id>/
        4. Cleans up worktree
        """
        import shlex

        qwex_home = self.config.qwex_home.rstrip("/")
        repo_path = f"{qwex_home}/repos/{workspace_name}.git"
        space_path = f"{qwex_home}/spaces/{run_id}"
        run_path = f"{qwex_home}/runs/{run_id}"

        cmd_str = shlex.join([command, *args])

        # Build the remote script
        script = f"""
set -e

# Ensure directories exist
mkdir -p {qwex_home}/repos {qwex_home}/spaces {qwex_home}/runs

# Create run directory
mkdir -p {run_path}

# Log status: running
echo '{{"status": "running", "ts": "'$(date -u +%Y-%m-%dT%H:%M:%S+00:00)'"}}' >> {run_path}/statuses.jsonl

# Create worktree from commit
cd {repo_path}
git worktree add --detach {space_path} {commit}

# Run command
cd {space_path}
{cmd_str} > {run_path}/stdout.log 2>&1
EXIT_CODE=$?

# Log status based on exit code
if [ $EXIT_CODE -eq 0 ]; then
    echo '{{"status": "succeeded", "ts": "'$(date -u +%Y-%m-%dT%H:%M:%S+00:00)'"}}' >> {run_path}/statuses.jsonl
else
    echo '{{"status": "failed", "ts": "'$(date -u +%Y-%m-%dT%H:%M:%S+00:00)'"}}' >> {run_path}/statuses.jsonl
fi

# Cleanup worktree
cd {repo_path}
git worktree remove --force {space_path} || true

exit $EXIT_CODE
"""
        return script.strip()
