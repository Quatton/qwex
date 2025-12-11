"""Component schema definitions for qwex.

Components are reusable building blocks (executors, storages, hooks).
Each component has:
  - name: identifier
  - vars: configurable variables with defaults
  - scripts: named scripts that can be invoked
"""

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
import yaml


class VarSpec(BaseModel):
    """Specification for a component variable."""

    required: bool = False
    default: str | int | bool | None = None
    description: str | None = None
    flag: str | None = Field(default=None, description="CLI flag name (without --)")


class Script(BaseModel):
    """A script that can be executed."""

    run: str | list[str] = Field(description="Command(s) to run")
    description: str | None = None


class Component(BaseModel):
    """A reusable component (executor, storage, hook)."""

    name: str
    kind: Literal["executor", "storage", "hook"]
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
        uses: Component reference (e.g., "executors/ssh" or "executors/ssh.yaml")
        project_root: Project root directory (containing .qwex/)

    Returns:
        Resolved path to the component YAML file

    Raises:
        FileNotFoundError: If component not found in any location
    """
    # Normalize: strip .yaml if present, we'll add it back
    ref = uses.removesuffix(".yaml")

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
