"""POSIX script builder for run lifecycle"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field


@dataclass
class RunSpec:
    """Intermediate representation for a run - compiles to POSIX sh"""

    run_id: str
    workspace_name: str
    command: list[str]
    qwex_home: str = "~/.qwex"

    # Optional: for worktree isolation
    commit: str | None = None
    repo_path: str | None = None  # e.g., ~/.qwex/repos/workspace.git

    # Lifecycle hooks (shell commands)
    init: list[str] = field(default_factory=list)
    cleanup: list[str] = field(default_factory=list)

    # Output handling
    stream_output: bool = True  # Use tee vs redirect

    def _paths(self) -> tuple[str, str, str]:
        """Return (run_path, space_path, repo_path)"""
        qh = self.qwex_home.rstrip("/")
        run_path = f"{qh}/runs/{self.run_id}"
        space_path = f"{qh}/spaces/{self.run_id}"
        repo_path = self.repo_path or f"{qh}/repos/{self.workspace_name}.git"
        return run_path, space_path, repo_path

    def with_worktree(self) -> "RunSpec":
        """Add worktree init/cleanup hooks"""
        if not self.commit:
            return self

        run_path, space_path, repo_path = self._paths()

        worktree_init = [
            f"cd {repo_path}",
            f"git worktree add --detach {space_path} {self.commit} 2>/dev/null",
            f"cd {space_path}",
        ]

        worktree_cleanup = [
            "cd /",
            f"git -C {repo_path} worktree remove --force {space_path} 2>/dev/null || rm -rf {space_path}",
        ]

        return RunSpec(
            run_id=self.run_id,
            workspace_name=self.workspace_name,
            command=self.command,
            qwex_home=self.qwex_home,
            commit=self.commit,
            repo_path=self.repo_path,
            init=self.init + worktree_init,
            cleanup=worktree_cleanup + self.cleanup,  # cleanup in reverse order
            stream_output=self.stream_output,
        )

    def with_status_reporting(self) -> "RunSpec":
        """Add status reporting hooks"""
        run_path, _, _ = self._paths()

        status_init = [
            f"mkdir -p {run_path}",
            f'echo \'{{"status": "running", "ts": "\'$(date -u +%Y-%m-%dT%H:%M:%S+00:00)\'"}}\' >> {run_path}/statuses.jsonl',
        ]

        # Note: status cleanup is handled in compile() based on exit code
        return RunSpec(
            run_id=self.run_id,
            workspace_name=self.workspace_name,
            command=self.command,
            qwex_home=self.qwex_home,
            commit=self.commit,
            repo_path=self.repo_path,
            init=status_init + self.init,
            cleanup=self.cleanup,
            stream_output=self.stream_output,
        )

    def with_dirs(self) -> "RunSpec":
        """Ensure qwex directories exist"""
        qh = self.qwex_home.rstrip("/")
        dir_init = [f"mkdir -p {qh}/repos {qh}/spaces {qh}/runs"]

        return RunSpec(
            run_id=self.run_id,
            workspace_name=self.workspace_name,
            command=self.command,
            qwex_home=self.qwex_home,
            commit=self.commit,
            repo_path=self.repo_path,
            init=dir_init + self.init,
            cleanup=self.cleanup,
            stream_output=self.stream_output,
        )

    def compile(self) -> str:
        """Compile to POSIX shell script"""
        run_path, _, _ = self._paths()
        cmd_str = shlex.join(self.command)

        # Build cleanup trap
        cleanup_cmds = (
            "\n".join(f"  {cmd}" for cmd in self.cleanup) if self.cleanup else "  :"
        )

        # Build init section
        init_section = "\n".join(self.init) if self.init else ":"

        # Output handling
        # Note: PIPESTATUS is bash-only. For POSIX, we use a different approach:
        # Run command, capture exit code, then tee separately won't work.
        # Solution: use a subshell and capture its exit code
        if self.stream_output:
            # Wrap command to capture exit code before tee
            run_cmd = f"{{ {cmd_str}; echo $? > /tmp/qwex_exit_$$.tmp; }} 2>&1 | tee {run_path}/stdout.log; EXIT_CODE=$(cat /tmp/qwex_exit_$$.tmp); rm -f /tmp/qwex_exit_$$.tmp"
            exit_code_capture = ""  # Already captured in run_cmd
        else:
            run_cmd = f"{cmd_str} > {run_path}/stdout.log 2>&1"
            exit_code_capture = "EXIT_CODE=$?"

        return f"""#!/bin/sh
set -e

# Cleanup trap
cleanup() {{
{cleanup_cmds}
}}
trap cleanup EXIT

# Init
{init_section}

# Run
{run_cmd}
{exit_code_capture}

# Status reporting
if [ "$EXIT_CODE" -eq 0 ]; then
    echo '{{"status": "succeeded", "ts": "'$(date -u +%Y-%m-%dT%H:%M:%S+00:00)'"}}' >> {run_path}/statuses.jsonl
else
    echo '{{"status": "failed", "ts": "'$(date -u +%Y-%m-%dT%H:%M:%S+00:00)'"}}' >> {run_path}/statuses.jsonl
fi

exit $EXIT_CODE
"""


def build_run_script(
    run_id: str,
    workspace_name: str,
    command: list[str],
    commit: str | None = None,
    qwex_home: str = "~/.qwex",
    repo_path: str
    | None = None,  # For local: workspace path. For remote: bare repo path.
    stream_output: bool = True,
) -> str:
    """
    Build a complete POSIX run script with worktree isolation and status reporting.

    Args:
        run_id: Unique run identifier
        workspace_name: Name of the workspace
        command: Command to execute as list
        commit: Git commit for worktree isolation (None = no worktree)
        qwex_home: Path to qwex home directory
        repo_path: Git repo path for worktree. Local: workspace dir. Remote: bare repo.
        stream_output: Use tee (True) or redirect (False)

    This is the main entry point for script generation.
    """
    spec = RunSpec(
        run_id=run_id,
        workspace_name=workspace_name,
        command=command,
        commit=commit,
        qwex_home=qwex_home,
        repo_path=repo_path,
        stream_output=stream_output,
    )

    # Chain the builders
    spec = spec.with_dirs()
    spec = spec.with_status_reporting()
    if commit:
        spec = spec.with_worktree()

    return spec.compile()
