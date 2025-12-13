"""Service layer for qwexcli commands."""

from pathlib import Path
from typing import Optional

from .project import scaffold
from .errors import QwexError, exit_with_error
from .context import CLIContext


class ProjectService:
    """Orchestrates project operations using CLI context."""

    def __init__(self, ctx: CLIContext) -> None:
        self.ctx = ctx

    def init(self, name: Optional[str] = None) -> None:
        """Initialize the project."""
        try:
            root = Path(self.ctx.cwd).resolve()
            qwex_yaml = root / "qwex.yaml"

            if qwex_yaml.exists() and not self.ctx.force:
                exit_with_error(
                    "qwex.yaml already exists (use --force to overwrite)", 1
                )

            scaffold(root=root, name=name)

        except QwexError as e:
            exit_with_error(e.message, e.exit_code)
        except Exception as e:
            exit_with_error(str(e), 1)
