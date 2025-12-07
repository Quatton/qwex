"""Service layer for qwexcli commands."""

import shutil
from typing import Optional

from .init import check_already_initialized, scaffold
from .errors import QwexError, exit_with_error
from .context import CLIContext


class ProjectService:
    """Orchestrates project operations using CLI context."""

    def __init__(self, ctx: CLIContext) -> None:
        self.ctx = ctx

    def init(self, name: Optional[str] = None) -> None:
        """Initialize the project."""
        try:
            qwex_dir = self.ctx.cwd / ".qwex"
            if self.ctx.force:
                if qwex_dir.exists():
                    shutil.rmtree(qwex_dir)
            else:
                check_already_initialized(cwd=self.ctx.cwd)

            scaffold(cwd=self.ctx.cwd, name=name)

        except QwexError as e:
            exit_with_error(e.message, e.exit_code)
        except Exception as e:
            exit_with_error(str(e), 1)
