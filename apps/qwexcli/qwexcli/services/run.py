"""Run service for qwex - orchestrates remote execution."""

from __future__ import annotations

import base64
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from qwexcli.lib.component import Component, load_component
from qwexcli.lib.template import interpolate, TemplateError


@dataclass
class RunConfig:
    """Configuration for a run."""

    # Executor config
    executor: str = "ssh"
    executor_vars: dict[str, Any] = field(default_factory=dict)

    # Storage config
    storage: str = "git_direct"
    storage_vars: dict[str, Any] = field(default_factory=dict)

    # Runtime
    project_name: str = "qwex"
    project_root: Path = field(default_factory=Path.cwd)


@dataclass
class RunContext:
    """Runtime context for a run."""

    run_id: str
    git_head: str
    command: str
    config: RunConfig


def generate_run_id(namespace: str) -> str:
    """Generate a unique run ID."""
    import random

    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    rand = f"{random.randint(0, 0xFFFF):04x}{random.randint(0, 0xFFFF):04x}"
    # Sanitize namespace
    ns = "".join(c if c.isalnum() else "-" for c in namespace.lower()).strip("-")
    return f"{ns}-{ts}-{rand}"


class RunService:
    """Orchestrates remote execution."""

    def __init__(self, config: RunConfig, components_dir: Path | None = None):
        self.config = config
        # Default to bundled templates if not specified
        self.components_dir = components_dir or (
            Path(__file__).parent.parent / "templates"
        )

    def _load_executor(self) -> Component:
        """Load the executor component."""
        path = self.components_dir / "executors" / f"{self.config.executor}.yaml"
        return load_component(str(path))

    def _load_storage(self) -> Component:
        """Load the storage component."""
        path = self.components_dir / "storages" / f"{self.config.storage}.yaml"
        return load_component(str(path))

    def _build_context(self, component: Component, extra_vars: dict[str, Any]) -> dict[str, Any]:
        """Build template context for a component."""
        # Start with component defaults
        vars_dict = component.get_var_defaults()
        # Override with config
        vars_dict.update(extra_vars)
        # Add project name
        vars_dict["PROJECT_NAME"] = self.config.project_name

        return {"vars": vars_dict, "inputs": {}, "env": dict(__import__("os").environ)}

    def push(self) -> str:
        """Push code using the storage component. Returns git HEAD."""
        storage = self._load_storage()
        vars_dict = storage.validate_vars(self.config.storage_vars)

        context = self._build_context(storage, vars_dict)
        script = storage.scripts["push"]

        # Interpolate the script
        run_cmd = script.run if isinstance(script.run, str) else "\n".join(script.run)  # type: ignore[union-attr]
        try:
            interpolated = interpolate(run_cmd, context)
        except TemplateError as e:
            print(f"[qwex] Template error: {e}", file=sys.stderr)
            sys.exit(1)

        # Execute locally
        print("[qwex] pushing code...")
        result = subprocess.run(
            ["bash", "-c", interpolated],
            cwd=self.config.project_root,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"[qwex] push failed:\n{result.stderr}", file=sys.stderr)
            sys.exit(result.returncode)

        git_head = result.stdout.strip().split("\n")[-1]
        print(f"[qwex] pushed: {git_head[:8]}")
        return git_head

    def run(self, command: str) -> int:
        """Run a command on the remote executor."""
        # Step 1: Push code
        git_head = self.push()

        # Step 2: Generate run ID
        run_id = generate_run_id(self.config.project_name)
        print(f"[qwex] run id: {run_id}")

        # Step 3: Build executor script
        executor = self._load_executor()
        vars_dict = executor.validate_vars(self.config.executor_vars)

        # Build context with inputs
        context = self._build_context(executor, vars_dict)
        context["inputs"] = {
            "git_head": git_head,
            "run_id": run_id,
            "command_b64": base64.b64encode(command.encode()).decode(),
        }

        script = executor.scripts["exec"]
        run_cmd = script.run if isinstance(script.run, str) else "\n".join(script.run)  # type: ignore[union-attr]

        try:
            remote_script = interpolate(run_cmd, context)
        except TemplateError as e:
            print(f"[qwex] Template error: {e}", file=sys.stderr)
            sys.exit(1)

        # Step 4: Execute on remote via SSH
        ssh_target = vars_dict.get("HOST", "")
        if vars_dict.get("USER"):
            ssh_target = f"{vars_dict['USER']}@{ssh_target}"

        ssh_port = vars_dict.get("PORT", 22)

        print(f"[qwex] executing on {ssh_target}...")

        # Stream the script to remote bash
        ssh_cmd = ["ssh", "-p", str(ssh_port), ssh_target, "bash", "-s"]

        proc = subprocess.Popen(
            ssh_cmd,
            stdin=subprocess.PIPE,
            text=True,
        )
        proc.communicate(input=remote_script)
        exit_code = proc.returncode

        print(f"[qwex] run complete: {run_id} (exit={exit_code})")
        return exit_code

    def status(self, run_id: str | None = None) -> dict[str, str]:
        """Get status of a run."""
        executor = self._load_executor()
        vars_dict = executor.validate_vars(self.config.executor_vars)

        ssh_target = vars_dict.get("HOST", "")
        if vars_dict.get("USER"):
            ssh_target = f"{vars_dict['USER']}@{ssh_target}"

        ssh_port = vars_dict.get("PORT", 22)
        run_dir = vars_dict.get("RUN_DIR", "$HOME/.qwex/runs")

        # Get latest run if not specified
        if not run_id:
            result = subprocess.run(
                ["ssh", "-p", str(ssh_port), ssh_target, f"ls -1t {run_dir} 2>/dev/null | head -1"],
                capture_output=True,
                text=True,
            )
            run_id = result.stdout.strip()
            if not run_id:
                return {"error": "no runs found"}

        # Fetch metadata
        meta_cmd = f"""
        cat {run_dir}/{run_id}/meta/status 2>/dev/null || echo unknown
        cat {run_dir}/{run_id}/meta/commit 2>/dev/null || echo unknown
        cat {run_dir}/{run_id}/meta/started_at 2>/dev/null || echo unknown
        cat {run_dir}/{run_id}/meta/finished_at 2>/dev/null || echo unknown
        cat {run_dir}/{run_id}/meta/exit_code 2>/dev/null || echo unknown
        """

        result = subprocess.run(
            ["ssh", "-p", str(ssh_port), ssh_target, meta_cmd],
            capture_output=True,
            text=True,
        )

        lines = result.stdout.strip().split("\n")
        return {
            "run_id": run_id,
            "status": lines[0] if len(lines) > 0 else "unknown",
            "commit": lines[1] if len(lines) > 1 else "unknown",
            "started": lines[2] if len(lines) > 2 else "unknown",
            "finished": lines[3] if len(lines) > 3 else "unknown",
            "exit_code": lines[4] if len(lines) > 4 else "unknown",
        }

    def list_runs(self) -> list[str]:
        """List all runs."""
        executor = self._load_executor()
        vars_dict = executor.validate_vars(self.config.executor_vars)

        ssh_target = vars_dict.get("HOST", "")
        if vars_dict.get("USER"):
            ssh_target = f"{vars_dict['USER']}@{ssh_target}"

        ssh_port = vars_dict.get("PORT", 22)
        run_dir = vars_dict.get("RUN_DIR", "$HOME/.qwex/runs")

        result = subprocess.run(
            ["ssh", "-p", str(ssh_port), ssh_target, f"ls -1t {run_dir} 2>/dev/null"],
            capture_output=True,
            text=True,
        )

        return [r for r in result.stdout.strip().split("\n") if r]

    def cancel(self, run_id: str | None = None) -> bool:
        """Cancel a running job."""
        executor = self._load_executor()
        vars_dict = executor.validate_vars(self.config.executor_vars)

        ssh_target = vars_dict.get("HOST", "")
        if vars_dict.get("USER"):
            ssh_target = f"{vars_dict['USER']}@{ssh_target}"

        ssh_port = vars_dict.get("PORT", 22)
        run_dir = vars_dict.get("RUN_DIR", "$HOME/.qwex/runs")

        # Get latest run if not specified
        if not run_id:
            runs = self.list_runs()
            if not runs:
                print("[qwex] no runs found")
                return False
            run_id = runs[0]

        print(f"[qwex] cancelling {run_id}...")

        # Get PID and kill
        cancel_cmd = f"""
        PID=$(cat {run_dir}/{run_id}/meta/pid 2>/dev/null)
        if [ -n "$PID" ]; then
            kill -TERM $PID 2>/dev/null || kill -KILL $PID 2>/dev/null || true
            echo "cancelled" > {run_dir}/{run_id}/meta/status
            echo "killed pid $PID"
        else
            echo "no pid found"
        fi
        """

        result = subprocess.run(
            ["ssh", "-p", str(ssh_port), ssh_target, cancel_cmd],
            capture_output=True,
            text=True,
        )

        print(f"[qwex] {result.stdout.strip()}")
        return "killed" in result.stdout

    def logs(self, run_id: str | None = None) -> tuple[str, str]:
        """Get logs for a run. Returns (stdout, stderr)."""
        executor = self._load_executor()
        vars_dict = executor.validate_vars(self.config.executor_vars)

        ssh_target = vars_dict.get("HOST", "")
        if vars_dict.get("USER"):
            ssh_target = f"{vars_dict['USER']}@{ssh_target}"

        ssh_port = vars_dict.get("PORT", 22)
        run_dir = vars_dict.get("RUN_DIR", "$HOME/.qwex/runs")

        # Get latest run if not specified
        if not run_id:
            runs = self.list_runs()
            if not runs:
                return ("", "no runs found")
            run_id = runs[0]

        stdout_result = subprocess.run(
            ["ssh", "-p", str(ssh_port), ssh_target, f"cat {run_dir}/{run_id}/logs/stdout.log 2>/dev/null"],
            capture_output=True,
            text=True,
        )

        stderr_result = subprocess.run(
            ["ssh", "-p", str(ssh_port), ssh_target, f"cat {run_dir}/{run_id}/logs/stderr.log 2>/dev/null"],
            capture_output=True,
            text=True,
        )

        return (stdout_result.stdout, stderr_result.stdout)

    def pull(self, run_id: str | None = None, local_dir: Path | None = None) -> Path:
        """Pull run logs to local. Returns local path."""
        executor = self._load_executor()
        vars_dict = executor.validate_vars(self.config.executor_vars)

        ssh_target = vars_dict.get("HOST", "")
        if vars_dict.get("USER"):
            ssh_target = f"{vars_dict['USER']}@{ssh_target}"

        ssh_port = vars_dict.get("PORT", 22)
        run_dir = vars_dict.get("RUN_DIR", "$HOME/.qwex/runs")

        local_dir = local_dir or (self.config.project_root / ".qwex" / "_internal" / "runs")
        local_dir.mkdir(parents=True, exist_ok=True)

        # Get latest run if not specified
        if not run_id:
            runs = self.list_runs()
            if not runs:
                raise ValueError("no runs found")
            run_id = runs[0]

        print(f"[qwex] pulling {run_id}...")

        subprocess.run(
            [
                "rsync", "-avz", "--progress",
                "-e", f"ssh -p {ssh_port}",
                f"{ssh_target}:{run_dir}/{run_id}/",
                str(local_dir / run_id) + "/",
            ],
            check=True,
        )

        print(f"[qwex] pulled to {local_dir / run_id}")
        return local_dir / run_id
