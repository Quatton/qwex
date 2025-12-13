"""Configuration management for qwexcli.

New schema based on qwex.yaml spec:
- name: project name
- defaults: default argument values
- tasks: dict of task definitions
  - each task has args (defaults) and steps
  - each step has id, name, hint (for runbook), uses (plugin), with (params)
- modes: dict of mode overlays that provide step implementations
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator


class StepConfig(BaseModel):
    """A single step in a task."""

    model_config = {"populate_by_name": True}

    # Identity
    id: str | None = Field(
        default=None, description="Step identifier for mode overlay matching"
    )
    name: str | None = Field(default=None, description="Human-readable step name")
    hint: str | None = Field(default=None, description="Hint text for runbook mode")

    # Shorthand for shell steps (moved to with_.run automatically)
    run: str | list[str] | None = Field(
        default=None, description="Shorthand for std/shell step"
    )

    # Implementation (can be provided by mode overlay)
    uses: str | None = Field(
        default=None, description="Plugin reference (e.g., 'std/echo', 'std/base')"
    )
    with_: dict[str, Any] = Field(
        default_factory=dict,
        alias="with",
        description="Parameters to pass to the plugin",
    )

    @model_validator(mode="after")
    def normalize_run_shorthand(self) -> "StepConfig":
        """Normalize 'run:' shorthand to std/shell step.

        When 'run:' is specified without 'uses:', automatically set uses to
        std/shell and move run content to with_.run.
        """
        if self.run is not None:
            self.with_["run"] = self.run
            self.run = None  # Clear the shorthand field
            # Auto-set uses to std/shell if not specified
            if self.uses is None:
                self.uses = "std/shell"
        return self


class ModeStepOverlay(BaseModel):
    """Step implementation in a mode overlay."""

    model_config = {"populate_by_name": True}

    id: str = Field(description="Step ID to overlay")
    uses: str = Field(description="Plugin reference")
    with_: dict[str, Any] = Field(
        default_factory=dict,
        alias="with",
        description="Parameters to pass to the plugin",
    )


class TaskConfig(BaseModel):
    """A task definition."""

    name: str | None = Field(default=None, description="Human-readable task name")
    description: str | None = Field(default=None, description="Task description")
    args: dict[str, Any] = Field(
        default_factory=dict, description="Default argument values"
    )
    steps: list[StepConfig] = Field(
        default_factory=list, description="Steps to execute"
    )


class ModeTaskOverlay(BaseModel):
    """Task overlay in a mode - provides step implementations."""

    steps: list[ModeStepOverlay] = Field(
        default_factory=list, description="Step implementations"
    )


class ModeConfig(BaseModel):
    """A mode overlay that provides implementations for tasks.

    Can specify:
    - uses: default plugin(s) for all steps without explicit uses
    - tasks: per-task, per-step overlays
    """

    uses: list[str] = Field(
        default_factory=list, description="Default plugins for steps without uses"
    )
    tasks: dict[str, ModeTaskOverlay] = Field(
        default_factory=dict, description="Task overlays"
    )


class DefaultsConfig(BaseModel):
    """Default values for the project."""

    args: dict[str, Any] = Field(
        default_factory=dict, description="Default argument values"
    )
    preset: str | None = Field(
        default=None, description="Default preset to apply to tasks"
    )


class QwexConfig(BaseModel):
    """Main qwex.yaml configuration."""

    model_config = {"populate_by_name": True}

    name: str = Field(description="Project name")
    defaults: DefaultsConfig | None = Field(default=None, description="Default values")
    tasks: dict[str, TaskConfig] = Field(
        default_factory=dict, description="Task definitions"
    )
    modes: dict[str, ModeConfig] = Field(
        default_factory=dict, alias="presets", description="Mode/preset overlays"
    )


def apply_mode_overlay(
    task: TaskConfig, mode: ModeConfig, task_name: str
) -> TaskConfig:
    """Apply a mode overlay to a task, filling in step implementations.

    Mode can provide:
    1. Default uses: list of plugins applied to steps without explicit uses
    2. Task-specific overlays: per-step uses/with configurations
    """
    # Get default uses from mode (for steps without explicit uses)
    default_uses = mode.uses[0] if mode.uses else None

    # Get task-specific overlay if it exists
    task_overlay = mode.tasks.get(task_name)
    overlay_map = {}
    if task_overlay:
        overlay_map = {s.id: s for s in task_overlay.steps}

    # Create new steps with overlay applied
    new_steps = []
    for step in task.steps:
        step_id = step.id or step.name

        # Check for step-specific overlay first
        if step_id and step_id in overlay_map:
            ov = overlay_map[step_id]
            # Merge: keep base step's id/name/hint, use overlay's uses/with
            new_step = StepConfig(
                id=step.id,
                name=step.name,
                hint=step.hint,
                uses=ov.uses,
                with_=ov.with_,
            )
            new_steps.append(new_step)
        elif not step.uses and default_uses:
            # Apply default uses if step doesn't have one
            new_step = StepConfig(
                id=step.id,
                name=step.name,
                hint=step.hint,
                uses=default_uses,
                with_=step.with_,
            )
            new_steps.append(new_step)
        else:
            new_steps.append(step)

    return TaskConfig(
        name=task.name,
        description=task.description,
        args=task.args,
        steps=new_steps,
    )


def load_qwex_yaml(path: Path) -> QwexConfig:
    """Load qwex.yaml from path."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    return QwexConfig(**data)


def load_env_yaml(path: Path) -> dict[str, Any]:
    """Load .qwex/.env.yaml overrides if it exists."""
    if not path.exists():
        return {}

    with open(path) as f:
        data = yaml.safe_load(f)

    return data or {}


def merge_config(base: QwexConfig, overrides: dict[str, Any]) -> QwexConfig:
    """Merge .env.yaml overrides into the base config."""
    data = base.model_dump(by_alias=True)

    # Deep merge for tasks
    if "tasks" in overrides:
        for task_name, task_overrides in overrides["tasks"].items():
            if task_name in data["tasks"]:
                # Merge args
                if "args" in task_overrides:
                    data["tasks"][task_name]["args"].update(task_overrides["args"])
                # Replace steps if provided (not merge)
                if "steps" in task_overrides:
                    data["tasks"][task_name]["steps"] = task_overrides["steps"]
            else:
                data["tasks"][task_name] = task_overrides

    # Top-level overrides
    if "name" in overrides:
        data["name"] = overrides["name"]

    # Merge defaults
    if "defaults" in overrides:
        if data.get("defaults") is None:
            data["defaults"] = overrides["defaults"]
        else:
            if "args" in overrides["defaults"]:
                data["defaults"]["args"].update(overrides["defaults"]["args"])

    return QwexConfig(**data)


def save_qwex_yaml(config: QwexConfig, path: Path) -> None:
    """Save config to qwex.yaml."""
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(by_alias=True, exclude_none=True)

    with open(path, "w") as f:
        yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False)
