"""Renderer - converts BashScript IR to final bash text."""

from qwl.compiler.spec import BashScript, BashFunction


class Renderer:
    """Renders BashScript IR to bash text."""

    def render(self, script: BashScript) -> str:
        """Render a BashScript to executable bash text.

        Args:
            script: The BashScript IR to render.

        Returns:
            Complete bash script as a string.
        """
        parts = [script.preamble, ""]

        # Emit each function definition + dependency registration
        for fn in script.functions:
            parts.append(self._render_function(fn))
            parts.append("")

        # Entrypoint
        parts.append(script.entrypoint)

        return "\n".join(parts)

    def _render_function(self, fn: BashFunction) -> str:
        """Render a single BashFunction to bash text.

        Args:
            fn: The function to render.

        Returns:
            Bash function definition + module:register_dependency call.
        """
        lines = []

        # Function definition
        lines.append(f"{fn.name} () {{")
        for line in fn.body.strip().split("\n"):
            lines.append(f"  {line}")
        lines.append("}")

        # Dependency registration
        deps_str = " ".join(fn.dependencies)
        lines.append(f'module:register_dependency "{fn.name}" "{deps_str}"')

        return "\n".join(lines)
