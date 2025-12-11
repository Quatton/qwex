"""Simple template interpolation for qwex.

Supports GitHub Actions-style ${{ expr }} syntax.
Deliberately minimal - no loops, no filters, just variable lookup.
"""

import re
from typing import Any


class TemplateError(Exception):
    """Raised when template interpolation fails."""

    pass


def interpolate(template: str, context: dict[str, Any]) -> str:
    """Interpolate ${{ expr }} placeholders in template string.

    Supports:
      - ${{ vars.FOO }} - lookup context["vars"]["FOO"]
      - ${{ inputs.command }} - lookup context["inputs"]["command"]
      - ${{ env.HOME }} - lookup context["env"]["HOME"]

    Args:
        template: String with ${{ expr }} placeholders
        context: Dict with nested values to substitute

    Returns:
        Interpolated string

    Raises:
        TemplateError: If a referenced key doesn't exist

    Example:
        >>> interpolate("Hello ${{ vars.NAME }}", {"vars": {"NAME": "world"}})
        'Hello world'
    """
    pattern = re.compile(r"\$\{\{\s*([^}]+?)\s*\}\}")

    def replace(match: re.Match[str]) -> str:
        expr = match.group(1).strip()
        try:
            return str(_resolve(expr, context))
        except KeyError as e:
            raise TemplateError(f"Undefined variable in template: {expr}") from e

    return pattern.sub(replace, template)


def _resolve(expr: str, context: dict[str, Any]) -> Any:
    """Resolve a dotted expression like 'vars.FOO' against context."""
    parts = expr.split(".")
    value: Any = context

    for part in parts:
        if isinstance(value, dict):
            if part not in value:
                raise KeyError(part)
            value = value[part]
        else:
            raise KeyError(part)

    return value


def interpolate_dict(data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Recursively interpolate all string values in a dict."""
    result: dict[str, Any] = {}

    for key, value in data.items():
        if isinstance(value, str):
            result[key] = interpolate(value, context)
        elif isinstance(value, dict):
            result[key] = interpolate_dict(value, context)
        elif isinstance(value, list):
            result[key] = [
                interpolate(v, context) if isinstance(v, str) else v for v in value
            ]
        else:
            result[key] = value

    return result
