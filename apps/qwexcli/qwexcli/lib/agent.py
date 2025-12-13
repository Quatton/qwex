"""Agent abstraction for qwex.

Agents are responsible for executing compiled payloads.
Each agent knows how to cross a specific boundary:
- local: just eval the payload
- ssh: send payload over SSH
- slurm: submit payload via sbatch
- docker: run payload in container
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class Agent(ABC):
    """Base class for execution agents.

    An agent receives a self-contained bash payload and executes it
    in its target environment. The payload contains everything needed:
    - Qwex kernel (core functions)
    - Context (run_id, args, env vars)
    - Plugin functions
    - Task steps
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent name for logging."""
        ...

    @abstractmethod
    def execute(
        self,
        payload: str,
        context: dict[str, Any],
        cwd: Path,
    ) -> int:
        """Execute a payload and return exit code.

        Args:
            payload: Self-contained bash script
            context: Execution context (for agent-level config, not payload)
            cwd: Working directory

        Returns:
            Exit code from execution
        """
        ...


class LocalAgent(Agent):
    """Execute payload locally via bash.

    This is the simplest agent - it just runs the payload in a subprocess.
    Conceptually: `bash -c "$payload"`
    """

    @property
    def name(self) -> str:
        return "local"

    def execute(
        self,
        payload: str,
        context: dict[str, Any],
        cwd: Path,
    ) -> int:
        """Execute payload locally.

        The payload is written to a temp file and executed with bash.
        Environment variables from context are injected.
        """
        # Write payload to temp file
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".sh",
            delete=False,
            prefix="qwex_payload_",
        ) as f:
            f.write(payload)
            script_path = f.name

        try:
            # Set up environment - inject QWEX_* vars
            env = os.environ.copy()
            env["QWEX_HOME"] = str(cwd)
            env["QWEX_RUN_ID"] = context.get("run_id", "unknown")
            env["QWEX_TASK"] = context.get("task_name", "unknown")

            # Execute
            result = subprocess.run(
                ["bash", script_path],
                cwd=cwd,
                env=env,
            )
            return result.returncode
        finally:
            os.unlink(script_path)


def get_agent(agent_name: str) -> Agent:
    """Get an agent by name.

    Currently only 'local' is supported.
    Future: ssh, slurm, docker, kubectl
    """
    agents = {
        "local": LocalAgent(),
    }

    if agent_name not in agents:
        available = ", ".join(agents.keys())
        raise ValueError(f"Agent '{agent_name}' not found. Available: {available}")

    return agents[agent_name]
