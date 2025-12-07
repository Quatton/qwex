"""Shared error handling for qwexcli."""

import sys
from typing import NoReturn

import typer


class QwexError(Exception):
    """Base exception for qwex operations."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        self.message = message
        self.exit_code = exit_code
        super().__init__(message)


def exit_with_error(message: str, exit_code: int = 1) -> NoReturn:
    """Exit the program with an error message."""
    typer.echo(f"Error: {message}", err=True)
    sys.exit(exit_code)


def handle_error(error: Exception) -> NoReturn:
    """Handle and exit on qwex errors."""
    if isinstance(error, QwexError):
        exit_with_error(error.message, error.exit_code)
    else:
        # Unexpected error
        typer.echo(f"Unexpected error: {error}", err=True)
        sys.exit(1)
