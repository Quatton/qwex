"""Renderer - converts BashScript IR to final bash text."""

import re
from qwl.compiler.spec import BashScript, BashFunction


class Renderer:
    """Renders BashScript IR to bash text."""

    # Pattern to detect heredoc start: <<'DELIM' or <<"DELIM" or <<DELIM
    # Delimiter can start with letter/digit/underscore (e.g., 8CHAR123)
    HEREDOC_START = re.compile(r"<<-?['\"]?([A-Za-z0-9_]+)['\"]?")

    def render(self, script: BashScript) -> str:
        """Render a BashScript to executable bash text.

        Args:
            script: The BashScript IR to render.

        Returns:
            Complete bash script as a string.
        """
        parts = [script.preamble, script.header.strip(), ""]

        # Emit each function definition + dependency registration
        for fn in script.functions:
            parts.append(self._render_function(fn))
            parts.append("")

        # Entrypoint
        parts.append(script.entrypoint)
        parts.append("")  # Trailing newline

        return "\n".join(parts)

    def _render_function(self, fn: BashFunction) -> str:
        """Render a single BashFunction to bash text.

        Args:
            fn: The function to render.

        Returns:
            Bash function definition + module:register_dependency call.
        """
        lines = []
        lines.append(f"{fn.name} () {{")

        # Process body with heredoc awareness
        body_lines = fn.body.strip().split("\n")
        active_heredocs: list[str] = []  # Stack of heredoc delimiters

        for line in body_lines:
            stripped = line.strip()

            # Check for heredoc start
            match = self.HEREDOC_START.search(line)
            if match:
                active_heredocs.append(match.group(1))

            # Check if this line is a heredoc terminator
            if active_heredocs and stripped == active_heredocs[-1]:
                # Don't indent heredoc terminators
                lines.append(stripped)
                active_heredocs.pop()
            else:
                # Normal indentation
                lines.append(f"  {line}")

        lines.append("}")

        # Dependency registration
        deps_str = " ".join(fn.dependencies)
        lines.append(f'module:register_dependency "{fn.name}" "{deps_str}"')

        return "\n".join(lines)
