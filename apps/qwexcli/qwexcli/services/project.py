"""Project-level services for qwexcli.

ProjectService is responsible for discovering the project root, computing
the config path, and orchestrating lib helpers while remaining CLI-aware
(force flag, non-interactive behavior, etc.).
"""

import shutil
from pathlib import Path
from typing import Optional

from qwexcli.lib.project import (
    check_already_initialized,
    find_project_root,
    scaffold,
)
from qwexcli.lib.context import CLIContext
from qwexcli.lib.errors import QwexError, exit_with_error


class ProjectService:
    """Service that orchestrates project-level operations for CLI commands."""

    def __init__(self, ctx: CLIContext) -> None:
        self.ctx = ctx

    def init(self, name: Optional[str] = None) -> Path:
        """Initialize the project.

        Resolves the project root and config path, enforces force semantics,
        and calls lower-level scaffolding helpers.
        """
        try:
            project_root = find_project_root(self.ctx.cwd)
            config_path = Path(project_root) / ".qwex" / "config.yaml"

            if self.ctx.force:
                if config_path.parent.exists():
                    shutil.rmtree(config_path.parent)
            else:
                check_already_initialized(config_path)

            return scaffold(config_path=config_path, name=name)

        except QwexError as e:
            exit_with_error(e.message, e.exit_code)
        except Exception as e:
            exit_with_error(str(e), 1)
