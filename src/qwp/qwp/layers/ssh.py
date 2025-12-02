"""SSH remote execution layer"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from qwp.layers import Layer, LayerContext, ShellCommand

if TYPE_CHECKING:
    from qwp.config import LayerConfig


class SSHLayerConfig:
    """Configuration for SSH layer"""

    def __init__(
        self,
        host: str,
        user: str | None = None,
        key_file: str | None = None,
        port: int = 22,
        config: str | None = None,
        workdir: str | None = None,
        qwex_home: str | None = None,  # remote QWEX_HOME override
        extra_args: list[str] | None = None,
    ):
        self.host = host
        self.user = user
        self.key_file = key_file
        self.port = port
        self.config = config
        self.workdir = workdir
        self.qwex_home = qwex_home or "~/.qwex"
        self.extra_args = extra_args or []

    @classmethod
    def from_layer_config(cls, config: "LayerConfig") -> "SSHLayerConfig":
        """Create SSHLayerConfig from generic LayerConfig"""
        if not config.host:
            raise ValueError("SSH layer requires 'host'")

        # Expand ~ in paths (local paths only)
        config_path = None
        if config.config:
            config_path = str(Path(config.config).expanduser())

        key_file = None
        if config.key_file:
            key_file = str(Path(config.key_file).expanduser())

        # Support both 'workdir' and 'cwd' fields
        workdir = config.workdir or config.cwd

        # Get qwex_home from extra fields
        qwex_home = getattr(config, "qwex_home", None)

        return cls(
            host=config.host,
            user=config.user,
            key_file=key_file,
            port=config.port or 22,
            config=config_path,
            workdir=workdir,
            qwex_home=qwex_home,
            extra_args=config.extra_args or [],
        )


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

    def __init__(self, config: "SSHLayerConfig | LayerConfig | dict[str, Any]"):
        """Accept SSHLayerConfig, LayerConfig, or dict and normalize."""
        if isinstance(config, SSHLayerConfig):
            self.config = config
        elif isinstance(config, dict):
            # Build from dict
            self.config = SSHLayerConfig(
                host=config["host"],
                user=config.get("user"),
                key_file=config.get("key_file"),
                port=config.get("port", 22),
                config=config.get("config"),
                workdir=config.get("workdir") or config.get("cwd"),
                extra_args=config.get("extra_args"),
            )
        else:
            # LayerConfig
            self.config = SSHLayerConfig.from_layer_config(config)

    def wrap(self, inner: ShellCommand, ctx: LayerContext) -> ShellCommand:
        """Wrap command to run on remote host via SSH"""
        args: list[str] = []

        # Add config file if specified (allows using aliases like 'csc')
        if self.config.config:
            args.extend(["-F", self.config.config])

        # Add key file if specified
        if self.config.key_file:
            args.extend(["-i", self.config.key_file])

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
        workdir = self.config.workdir
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

        if self.config.config:
            args.extend(["-F", self.config.config])

        if self.config.key_file:
            args.extend(["-i", self.config.key_file])

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

        qwex_home = self.config.qwex_home
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
