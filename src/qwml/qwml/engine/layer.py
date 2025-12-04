"""Base Layer class - the core abstraction.

A Layer is like a React component:
- Takes props (dataclass fields)
- Has a render() method that returns shell script
- Can be composed with other layers
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader


@dataclass
class Layer(ABC):
    """Base class for execution layers.

    Like a React component: takes props, returns rendered output.

    Each layer produces a shell function body that:
    1. Does its setup
    2. Calls "$@" (the next layer)
    3. Does its cleanup
    """

    @abstractmethod
    def render(self, ctx: dict[str, Any]) -> str:
        """Render this layer to shell script.

        Args:
            ctx: Context dict (like React's context)

        Returns:
            Shell script fragment
        """
        pass

    @property
    def name(self) -> str:
        """Layer name for debugging."""
        return self.__class__.__name__


@dataclass
class TemplateLayer(Layer):
    """A layer that renders from a Jinja2 template.

    This is the workhorse - most layers should use this.
    Like a React component that returns JSX (but it's shell).

    Usage:
        layer = TemplateLayer(
            template_path="noop.sh.j2",
            props={"some_var": "value"},
        )
        output = layer.render(ctx)
    """

    # Path to template file (relative to templates dir or absolute)
    template: str

    # Props passed to the template (like React props)
    props: dict[str, Any] = field(default_factory=dict)

    # Optional custom name
    layer_name: str | None = None

    # Template loader (defaults to built-in templates)
    _env: Environment | None = field(default=None, repr=False)

    def render(self, ctx: dict[str, Any]) -> str:
        """Render the template with props and context merged."""
        env = self._get_env()
        template = env.get_template(self.template)

        # Merge props and ctx (props take precedence)
        variables = {**ctx, **self.props}
        return template.render(**variables)

    def _get_env(self) -> Environment:
        """Get or create Jinja2 environment."""
        if self._env is not None:
            return self._env

        # Default: look in qwml/templates/
        templates_dir = Path(__file__).parent.parent / "templates"
        return Environment(
            loader=FileSystemLoader(str(templates_dir)),
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    @property
    def name(self) -> str:
        if self.layer_name:
            return self.layer_name
        # Extract name from template path: "foo/bar.sh.j2" -> "bar"
        return Path(self.template).stem.removesuffix(".sh")


@dataclass
class InlineLayer(Layer):
    """A layer with inline shell script (no template file).

    Useful for quick one-offs or dynamically generated scripts.
    """

    script: str
    layer_name: str = "inline"

    def render(self, ctx: dict[str, Any]) -> str:
        # Simple string interpolation with ctx
        # For complex logic, use TemplateLayer instead
        return self.script

    @property
    def name(self) -> str:
        return self.layer_name


# Factory functions (like React.createElement shorthand)


def template(
    template: str,
    props: dict[str, Any] | None = None,
    name: str | None = None,
) -> TemplateLayer:
    """Create a template-based layer.

    Args:
        template: Template file path (e.g., "noop.sh.j2")
        props: Variables to pass to template
        name: Optional layer name
    """
    return TemplateLayer(
        template=template,
        props=props or {},
        layer_name=name,
    )


def inline(script: str, name: str = "inline") -> InlineLayer:
    """Create an inline script layer."""
    return InlineLayer(script=script, layer_name=name)
