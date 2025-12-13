"""Task runner and bash compiler for qwex.

This module handles:
1. Loading qwex.yaml and .qwex/.env.yaml
2. Generating run IDs
3. Resolving Jinja2 templates in step parameters
4. Applying mode overlays to tasks
5. Compiling tasks to executable bash scripts
6. Executing the compiled scripts
"""

from __future__ import annotations

import os
import random
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, BaseLoader, UndefinedError

from qwexcli.lib.config import (
    QwexConfig,
    TaskConfig,
    load_qwex_yaml,
    load_env_yaml,
    merge_config,
    apply_mode_overlay,
)
from qwexcli.lib.plugin import get_plugin, Plugin


def generate_run_id() -> str:
    """Generate a lexicographically sortable unique run ID.

    Format: YYYYMMDD_HHMMSS_xxxxxxxx (8 random hex chars)
    Example: 20231212_153045_a1b2c3d4
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    rand = f"{random.randint(0, 0xFFFFFFFF):08x}"
    return f"{ts}_{rand}"


class JinjaRenderer:
    """Renders Jinja2 templates with the task context."""

    def __init__(self, context: dict[str, Any]):
        self.context = context
        self.env = Environment(loader=BaseLoader(), autoescape=False)

    def render(self, template_str: str) -> str:
        """Render a template string with the current context."""
        try:
            template = self.env.from_string(template_str)
            return template.render(**self.context)
        except UndefinedError as e:
            raise ValueError(f"Undefined variable in template: {e}")

    def render_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively render all string values in a dict."""
        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.render(value)
            elif isinstance(value, dict):
                result[key] = self.render_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    self.render(v) if isinstance(v, str) else v for v in value
                ]
            else:
                result[key] = value
        return result


class BashCompiler:
    """Compiles a task to an executable bash script (payload).

    The compiled script is self-contained and includes:
    - QWEX_KERNEL: Core runtime functions
    - QWEX_CONTEXT: Run ID, task name, args (as bash variables)
    - Plugin functions: Only those actually used
    - Task steps: The actual work to do
    """

    # The micro-kernel - minimal runtime for executing steps
    # This gets embedded in every payload, making it self-contained
    QWEX_KERNEL = """
# ═══════════════════════════════════════════════════════════
# QWEX KERNEL - Micro-runtime for task execution
# ═══════════════════════════════════════════════════════════

# Safety: fail on undefined variables
set -u

# Color support (graceful degradation for non-TTY)
if [ -t 1 ]; then
    __Q_RED='\\033[0;31m'
    __Q_GREEN='\\033[0;32m'
    __Q_BLUE='\\033[0;34m'
    __Q_GRAY='\\033[0;90m'
    __Q_RESET='\\033[0m'
else
    __Q_RED='' __Q_GREEN='' __Q_BLUE='' __Q_GRAY='' __Q_RESET=''
fi

# Core step runner with timing and error handling
q_run_step() {
    local step_name="$1"
    local command_str="$2"
    local start_time=$(date +%s)

    echo -e "\\n${__Q_GRAY}┌── ${__Q_BLUE}Step: ${step_name}${__Q_RESET}"
    echo -e "${__Q_GRAY}│ ${command_str}${__Q_RESET}"

    # Execute with eval to support complex shell strings
    eval "$command_str"
    local exit_code=$?

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    if [ $exit_code -eq 0 ]; then
        echo -e "${__Q_GRAY}└─ ${__Q_GREEN}✔ Success${__Q_GRAY} (${duration}s)${__Q_RESET}"
        return 0
    else
        echo -e "${__Q_GRAY}└─ ${__Q_RED}✘ Failed${__Q_GRAY} (exit: ${exit_code})${__Q_RESET}"
        exit $exit_code
    fi
}

# Logging helpers
q_log() { echo -e "${__Q_BLUE}[qwex]${__Q_RESET} $1"; }
q_error() { echo -e "${__Q_RED}[qwex]${__Q_RESET} $1" >&2; }
"""

    def __init__(self, context: dict[str, Any] | None = None):
        self.context = context or {}
        self.plugin_functions: dict[str, str] = {}
        self.steps: list[tuple[str, str]] = []  # (name, command)

    def add_step(self, name: str, plugin: Plugin, params: dict[str, Any]) -> None:
        """Add a step to the script."""
        # Register plugin function if not already
        if plugin.full_name not in self.plugin_functions:
            func_def = plugin.compile_function()
            if func_def:  # Some plugins (like shell) have no function
                self.plugin_functions[plugin.full_name] = func_def

        # Compile the call
        call = plugin.compile_call(params)
        self.steps.append((name, call))

    def compile(self) -> str:
        """Compile to a self-contained bash payload.

        The payload structure:
        1. Shebang
        2. Kernel (core functions)
        3. Context (embedded variables)
        4. Plugin functions
        5. Steps
        6. Entrypoint
        """
        parts = ["#!/bin/bash"]

        # Add kernel
        parts.append(self.QWEX_KERNEL)

        # Add context as embedded variables (self-contained)
        parts.append("# ═══════════════════════════════════════════════════════════")
        parts.append("# QWEX CONTEXT - Embedded execution context")
        parts.append("# ═══════════════════════════════════════════════════════════")
        if self.context:
            run_id = self.context.get("run_id", "unknown")
            task_name = self.context.get("task_name", "unknown")
            qwex_home = self.context.get("qwex_home", "")
            workspace_name = self.context.get("workspace_name", "default")
            parts.append(f'__QWEX_RUN_ID="{run_id}"')
            parts.append(f'__QWEX_TASK="{task_name}"')
            parts.append(f'__QWEX_WORKSPACE="{workspace_name}"')
            # QWEX_HOME resolution order:
            # 1. Agent-provided QWEX_HOME (for remote execution)
            # 2. Compile-time path (for local execution)
            # 3. ~/.qwex/<workspace> (fallback for remote without agent)
            if qwex_home:
                parts.append(f'export QWEX_HOME="${{QWEX_HOME:-{qwex_home}}}"')
            else:
                parts.append(
                    f'export QWEX_HOME="${{QWEX_HOME:-$HOME/.qwex/{workspace_name}}}"'
                )
            # Export args as __QWEX_ARG_<name>
            args = self.context.get("args", {})
            for key, value in args.items():
                # Escape value for bash
                escaped = str(value).replace('"', '\\"')
                parts.append(f'__QWEX_ARG_{key}="{escaped}"')
        parts.append("")

        # Add plugin functions
        if self.plugin_functions:
            parts.append(
                "# ═══════════════════════════════════════════════════════════"
            )
            parts.append("# QWEX PLUGINS - Compiled plugin functions")
            parts.append(
                "# ═══════════════════════════════════════════════════════════"
            )
            for func in self.plugin_functions.values():
                parts.append(func)
            parts.append("")

        # Add entrypoint
        parts.append("# ═══════════════════════════════════════════════════════════")
        parts.append("# QWEX ENTRYPOINT - Task execution")
        parts.append("# ═══════════════════════════════════════════════════════════")
        parts.append("__qwex_main() {")
        parts.append('    q_log "run_id: $__QWEX_RUN_ID"')
        parts.append('    q_log "task: $__QWEX_TASK"')
        parts.append("")

        for i, (name, cmd) in enumerate(self.steps):
            step_name = name or f"step_{i + 1}"
            # Escape the command for embedding in bash string
            escaped_cmd = cmd.replace("'", "'\\''")
            parts.append(f"    q_run_step '{step_name}' '{escaped_cmd}'")

        parts.append("}")
        parts.append("")
        parts.append('__qwex_main "$@"')

        return "\n".join(parts)


class TaskRunner:
    """Runs tasks from qwex.yaml."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.qwex_yaml_path = project_root / "qwex.yaml"
        self.env_yaml_path = project_root / ".qwex" / ".env.yaml"

    def load_config(self) -> QwexConfig:
        """Load and merge config from qwex.yaml and .qwex/.env.yaml."""
        base = load_qwex_yaml(self.qwex_yaml_path)
        overrides = load_env_yaml(self.env_yaml_path)
        return merge_config(base, overrides)

    def get_task(
        self,
        config: QwexConfig,
        task_name: str,
        mode: str | None = None,
    ) -> TaskConfig:
        """Get a task by name, optionally applying a mode overlay."""
        if task_name not in config.tasks:
            available = ", ".join(config.tasks.keys()) or "(none)"
            raise ValueError(f"Task '{task_name}' not found. Available: {available}")

        task = config.tasks[task_name]

        # Apply mode overlay if specified
        if mode:
            if mode not in config.modes:
                available_modes = ", ".join(config.modes.keys()) or "(none)"
                raise ValueError(
                    f"Mode '{mode}' not found. Available: {available_modes}"
                )
            task = apply_mode_overlay(task, config.modes[mode], task_name)

        return task

    def build_context(
        self,
        config: QwexConfig,
        task: TaskConfig,
        run_id: str,
        cli_args: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the Jinja2 context for template rendering.

        Context resolution order:
        1. defaults.args from config
        2. task.args (can reference defaults via {{ defaults.args.X }})
        3. cli_args override everything
        """
        # Start with defaults
        defaults_args: dict[str, Any] = {}
        if config.defaults:
            defaults_args = dict(config.defaults.args)

        # Create a temporary context for rendering task.args
        # task.args values might contain {{ defaults.args.X }} templates
        temp_context = {
            "defaults": {"args": defaults_args},
            "run_id": run_id,
            "env": dict(os.environ),
        }
        temp_renderer = JinjaRenderer(temp_context)

        # Render task args (they may contain templates like "{{ defaults.args.ssh_host }}")
        task_args = {}
        for key, value in task.args.items():
            if isinstance(value, str):
                task_args[key] = temp_renderer.render(value)
            else:
                task_args[key] = value

        # CLI args override rendered task args
        task_args.update(cli_args)

        return {
            "args": task_args,
            "defaults": {"args": defaults_args},
            "run_id": run_id,
            "env": dict(os.environ),
        }

    def compile_task(
        self,
        task: TaskConfig,
        context: dict[str, Any],
        from_step: str | None = None,
        only_step: str | None = None,
        task_name: str = "unknown",
        workspace_name: str = "default",
    ) -> str:
        """Compile a task to a self-contained bash payload.

        Args:
            task: Task configuration
            context: Jinja2 context for template rendering
            from_step: If set, skip steps until this step (by id or name)
            only_step: If set, run only this specific step (by id or name)
            task_name: Name of the task (for embedding in payload)
            workspace_name: Name of the workspace (for remote QWEX_HOME fallback)
        """
        renderer = JinjaRenderer(context)

        # Build compiler context (what gets embedded in payload)
        compiler_context = {
            "run_id": context.get("run_id", "unknown"),
            "task_name": task_name,
            "args": context.get("args", {}),
            "qwex_home": str(self.project_root),
            "workspace_name": workspace_name,
        }
        compiler = BashCompiler(context=compiler_context)

        # Determine which steps to include
        steps_to_run = []
        found_from_step = from_step is None  # If not specified, start from beginning

        for i, step in enumerate(task.steps):
            step_id = step.id or step.name or f"step_{i + 1}"

            # Handle --from flag
            if from_step and not found_from_step:
                if step.id == from_step or step.name == from_step:
                    found_from_step = True
                else:
                    continue

            # Handle --step flag (only run specific step)
            if only_step:
                if step.id != only_step and step.name != only_step:
                    continue

            steps_to_run.append((i, step))

        if from_step and not found_from_step:
            raise ValueError(f"Step '{from_step}' not found in task")

        if only_step and not steps_to_run:
            raise ValueError(f"Step '{only_step}' not found in task")

        for i, step in steps_to_run:
            # Check if step has implementation
            if not step.uses:
                step_id = step.id or step.name or f"step_{i + 1}"
                raise ValueError(
                    f"Step '{step_id}' has no implementation (missing 'uses'). "
                    f"Use 'run:' shorthand or specify 'uses:' explicitly."
                )

            # Resolve plugin
            try:
                plugin = get_plugin(step.uses)
            except ValueError as e:
                raise ValueError(f"Step {i + 1}: {e}")

            # Build step context (includes step.hint for runbook)
            step_context = dict(context)
            step_context["step"] = {
                "id": step.id,
                "name": step.name,
                "hint": step.hint,
            }
            step_renderer = JinjaRenderer(step_context)

            # Render step params with Jinja2
            rendered_params = step_renderer.render_dict(step.with_)

            # Add to compiler
            step_name = step.name or step.id or f"step_{i + 1}"
            compiler.add_step(step_name, plugin, rendered_params)

        return compiler.compile()

    def run_task(
        self,
        task_name: str,
        cli_args: dict[str, Any] | None = None,
        mode: str | None = None,
        dry_run: bool = False,
        from_step: str | None = None,
        only_step: str | None = None,
    ) -> int:
        """Run a task by name.

        Args:
            task_name: Name of the task to run
            cli_args: CLI arguments to pass to the task (override task.args)
            mode: Mode/preset overlay to apply (e.g., 'auto', 'runbook')
            dry_run: If True, print the script but don't execute
            from_step: Start execution from this step (by id or name)
            only_step: Run only this specific step (by id or name)

        Returns:
            Exit code (0 for success)
        """
        cli_args = cli_args or {}

        # Load config
        config = self.load_config()

        # Use default preset if none specified
        effective_mode = mode
        if effective_mode is None and config.defaults and config.defaults.preset:
            effective_mode = config.defaults.preset

        # Get task (with mode overlay if specified)
        task = self.get_task(config, task_name, effective_mode)

        # Generate run ID
        run_id = generate_run_id()

        # Build context
        context = self.build_context(config, task, run_id, cli_args)

        # Compile task to payload (with step filtering)
        workspace_name = config.name or self.project_root.name
        payload = self.compile_task(
            task,
            context,
            from_step,
            only_step,
            task_name=task_name,
            workspace_name=workspace_name,
        )

        if dry_run:
            print(payload)
            return 0

        # Execute via local agent
        # The payload is self-contained - it has the kernel, context, and steps
        # The agent just needs to eval it
        from qwexcli.lib.agent import LocalAgent

        agent = LocalAgent()
        agent_context = {
            "run_id": run_id,
            "task_name": task_name,
            "preset": effective_mode,
            "from_step": from_step,
            "only_step": only_step,
        }

        return agent.execute(payload, agent_context, self.project_root)

    def list_tasks(self) -> list[str]:
        """List available tasks."""
        config = self.load_config()
        return list(config.tasks.keys())

    def list_modes(self) -> list[str]:
        """List available modes."""
        config = self.load_config()
        return list(config.modes.keys())
