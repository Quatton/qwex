"""Init command for qwexcli."""

import shutil
from pathlib import Path

from qwexcli.lib.errors import handle_error
from qwexcli.lib.init import check_already_initialized, scaffold_project
import typer


def init_command(force: bool = False) -> None:
    """Initialize qwex in the current directory."""
    try:
        # If force is used, remove existing .qwex directory
        if force:
            qwex_dir = Path(".qwex")
            if qwex_dir.exists():
                shutil.rmtree(qwex_dir)
        else:
            # 1. Check if already initialized (only if not force)
            check_already_initialized()
        
        # 2. Scaffold the project (for now just creates config)
        # TODO: Add prompting for required configs when needed
        scaffold_project()
        
        typer.echo("Initialized qwex in current directory")
        
    except Exception as e:
        handle_error(e)
