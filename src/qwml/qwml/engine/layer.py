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

    Supports two modes:
    1. File-based: template="ssh.sh.j2" (loads from templates dir)
    2. Inline: content="exec ssh {{ host }} \"$@\"" (template string)

    Like a React component - can be from a file or inline JSX.

    Usage:
        # From file
        layer = TemplateLayer(template="noop.sh.j2", props={"var": "value"})

        # Inline template
        layer = TemplateLayer(content='exec "$@"', props={})
    """

    # Option 1: Path to template file (relative to templates dir or absolute)
    template: str | None = None

    # Option 2: Inline template content
    content: str | None = None

    # Props passed to the template (like React props)
    props: dict[str, Any] = field(default_factory=dict)

    # Optional custom name
    layer_name: str | None = None

    # Template loader (defaults to built-in templates)
    _env: Environment | None = field(default=None, repr=False)

    def __post_init__(self):
        """Validate that exactly one of template or content is provided."""
        if self.template is None and self.content is None:
            raise ValueError("Must provide either 'template' or 'content'")
        if self.template is not None and self.content is not None:
            raise ValueError("Cannot provide both 'template' and 'content'")

    def render(self, ctx: dict[str, Any]) -> str:
        """Render the template with props and context merged."""
        env = self._get_env()

        if self.content is not None:
            # Inline template - compile from string
            tmpl = env.from_string(self.content)
        else:
            # File-based template
            tmpl = env.get_template(self.template)  # type: ignore

        # Merge props and ctx (props take precedence)
        variables = {**ctx, **self.props}
        return tmpl.render(**variables)

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
        if self.template:
            # Extract name from template path: "foo/bar.sh.j2" -> "bar"
            return Path(self.template).stem.removesuffix(".sh")
        return "inline"


@dataclass
class InlineLayer(Layer):
    """A layer with inline shell script (no template, no Jinja).

    For static scripts that don't need templating.
    Use TemplateLayer with content= for Jinja interpolation.
    """

    script: str
    layer_name: str = "inline"

    def render(self, ctx: dict[str, Any]) -> str:
        # No templating - return script as-is
        return self.script

    @property
    def name(self) -> str:
        return self.layer_name


# Factory functions (like React.createElement shorthand)


def template(
    path: str | None = None,
    *,
    content: str | None = None,
    props: dict[str, Any] | None = None,
    name: str | None = None,
) -> TemplateLayer:
    """Create a template-based layer.

    Args:
        path: Template file path (e.g., "noop.sh.j2")
        content: Inline template string (alternative to path)
        props: Variables to pass to template
        name: Optional layer name

    Examples:
        # From file
        template("ssh.sh.j2", props={"host": "cluster"})

        # Inline template with Jinja
        template(content='exec ssh {{ host }} "$@"', props={"host": "cluster"})
    """
    return TemplateLayer(
        template=path,
        content=content,
        props=props or {},
        layer_name=name,
    )


def inline(script: str, name: str = "inline") -> InlineLayer:
    """Create an inline script layer (no Jinja templating)."""
    return InlineLayer(script=script, layer_name=name)
