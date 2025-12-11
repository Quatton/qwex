"""Component schema definitions for qwex.

Components are reusable building blocks (executors, storages, hooks).
Each component has:
  - name: identifier
  - vars: configurable variables with defaults
  - scripts: named scripts that can be invoked
"""

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
import yaml


class VarSpec(BaseModel):
    """Specification for a component variable."""

    required: bool = False
    default: str | int | bool | None = None
    description: str | None = None
    flag: str | None = Field(default=None, description="CLI flag name (without --)")


class Step(BaseModel):
    """A single step in a workflow."""

    model_config = ConfigDict(populate_by_name=True)

    name: str | None = Field(default=None, description="Step name")
    uses: str | None = Field(default=None, description="Component to use (e.g., 'storages/git_direct:push')")
    with_: dict[str, Any] | None = Field(default=None, alias="with", description="Variables to pass to the component")
    run: str | list[str] | None = Field(default=None, description="Command(s) to run")

    def model_post_init(self, __context: Any) -> None:
        """Validate that either uses or run is provided."""
        if self.uses is None and self.run is None:
            raise ValueError("Step must have either 'uses' or 'run'")


class Script(BaseModel):
    """A script that can be executed."""

    run: str | list[str] | None = Field(default=None, description="Command(s) to run")
    steps: list[Step | dict[str, Any]] | None = Field(default=None, description="Workflow steps")
    description: str | None = None

    def model_post_init(self, __context: Any) -> None:
        """Normalize and validate script structure."""
        # Exactly one of run or steps must be provided
        if self.run is None and self.steps is None:
            raise ValueError("Script must have either 'run' or 'steps'")
        if self.run is not None and self.steps is not None:
            raise ValueError("Script cannot have both 'run' and 'steps'")
        
        # Normalize steps
        if self.steps is not None:
            normalized_steps: list[Step] = []
            for step_val in self.steps:
                if isinstance(step_val, Step):
                    normalized_steps.append(step_val)
                elif isinstance(step_val, dict):
                    normalized_steps.append(Step(**step_val))
                else:
                    raise ValueError(f"Invalid step value: {step_val}")
            object.__setattr__(self, "steps", normalized_steps)


class Component(BaseModel):
    """A reusable component (executor, storage, hook)."""

    name: str
    tags: list[str] = Field(default_factory=list, description="Component tags for categorization")
    description: str | None = None
    vars: dict[str, VarSpec | str | int | bool] = Field(default_factory=dict)
    scripts: dict[str, Script | str] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        """Normalize shorthand syntax to full objects."""
        # Normalize vars: "foo" -> VarSpec(default="foo")
        normalized_vars: dict[str, VarSpec] = {}
        for key, val in self.vars.items():
            if isinstance(val, VarSpec):
                normalized_vars[key] = val
            elif isinstance(val, dict):
                # Type ignore: Pydantic will validate at runtime
                normalized_vars[key] = VarSpec(**val)  # type: ignore[arg-type]
            else:
                normalized_vars[key] = VarSpec(default=val)
        object.__setattr__(self, "vars", normalized_vars)

        # Normalize scripts: "echo hi" -> Script(run="echo hi")
        normalized_scripts: dict[str, Script] = {}
        for key, val in self.scripts.items():
            if isinstance(val, Script):
                normalized_scripts[key] = val
            elif isinstance(val, str):
                normalized_scripts[key] = Script(run=val)
            elif isinstance(val, dict):
                normalized_scripts[key] = Script(**val)
            else:
                raise ValueError(f"Invalid script value for {key}: {val}")
        object.__setattr__(self, "scripts", normalized_scripts)

    def get_var_defaults(self) -> dict[str, Any]:
        """Get default values for all vars."""
        return {
            k: v.default
            for k, v in self.vars.items()
            if isinstance(v, VarSpec) and v.default is not None
        }

    def get_flaggable_vars(self) -> dict[str, VarSpec]:
        """Get vars that have CLI flags defined."""
        return {
            k: v
            for k, v in self.vars.items()
            if isinstance(v, VarSpec) and v.flag is not None
        }

    def validate_vars(self, provided: dict[str, Any]) -> dict[str, Any]:
        """Validate and fill in defaults for provided vars."""
        result = self.get_var_defaults()
        result.update(provided)

        # Check required vars
        for key, spec in self.vars.items():
            if isinstance(spec, VarSpec) and spec.required and key not in result:
                raise ValueError(
                    f"Required variable '{key}' not provided for component '{self.name}'"
                )

        return result


# --- Component Resolution ---


def parse_component_ref(uses: str) -> tuple[str, str | None]:
    """Parse a component reference into component path and function name.
    
    Args:
        uses: Component reference (e.g., "executors/ssh:exec" or "executors/ssh")
    
    Returns:
        Tuple of (component_path, function_name)
        If no function specified, function_name is None
    
    Examples:
        >>> parse_component_ref("executors/ssh:exec")
        ("executors/ssh", "exec")
        >>> parse_component_ref("executors/ssh")
        ("executors/ssh", None)
    """
    if ":" in uses:
        component_path, function_name = uses.split(":", 1)
        return component_path, function_name
    return uses, None


def get_bundled_templates_dir() -> Path:
    """Get the path to bundled templates."""
    return Path(__file__).parent.parent / "templates"


def resolve_component_path(
    uses: str,
    project_root: Path | None = None,
) -> Path:
    """Resolve a component reference to an actual file path.

    Resolution order:
    1. Project-local: .qwex/components/<uses>.yaml
    2. Bundled templates: qwexcli/templates/<uses>.yaml

    Args:
        uses: Component reference (e.g., "executors/ssh:exec", "executors/ssh" or "executors/ssh.yaml")
        project_root: Project root directory (containing .qwex/)

    Returns:
        Resolved path to the component YAML file

    Raises:
        FileNotFoundError: If component not found in any location
    """
    # Strip function name if present (e.g., "executors/ssh:exec" -> "executors/ssh")
    component_path, _ = parse_component_ref(uses)
    
    # Normalize: strip .yaml if present, we'll add it back
    ref = component_path.removesuffix(".yaml")

    candidates: list[Path] = []

    # 1. Project-local components
    if project_root:
        local_path = project_root / ".qwex" / "components" / f"{ref}.yaml"
        candidates.append(local_path)
        if local_path.exists():
            return local_path

    # 2. Bundled templates
    bundled_path = get_bundled_templates_dir() / f"{ref}.yaml"
    candidates.append(bundled_path)
    if bundled_path.exists():
        return bundled_path

    raise FileNotFoundError(
        f"Component '{uses}' not found. Searched:\n"
        + "\n".join(f"  - {p}" for p in candidates)
    )


def load_component(path: str | Path) -> Component:
    """Load a component from a YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return Component(**data)


def load_component_by_ref(
    uses: str,
    project_root: Path | None = None,
) -> Component:
    """Load a component by its reference string."""
    path = resolve_component_path(uses, project_root)
    return load_component(path)


def load_component_from_string(content: str) -> Component:
    """Load a component from a YAML string."""
    data = yaml.safe_load(content)
    return Component(**data)
