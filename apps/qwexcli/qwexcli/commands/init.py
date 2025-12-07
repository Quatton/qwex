"""Init command for qwexcli."""

from qwexcli.lib.errors import handle_error
from qwexcli.lib.init import check_already_initialized, scaffold_project
import typer


def init_command() -> None:
    """Initialize qwex in the current directory."""
    try:
        # 1. Check if already initialized
        check_already_initialized()

        # 2. Scaffold the project (for now just creates config)
        # TODO: Add prompting for required configs when needed
        scaffold_project()

        typer.echo("Initialized qwex in current directory")

    except Exception as e:
        handle_error(e)
