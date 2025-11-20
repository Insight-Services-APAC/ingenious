"""Tests the command registration wrapper for search functionalities.

This module verifies that the search-related CLI commands are correctly
registered with the main Typer application. It ensures that the
`register_commands` function successfully adds the `azure-search`
subcommand and its own subcommands (like `run`) to the application's
command structure. This is a simple integration test to confirm
CLI entry points are available.
"""

from __future__ import annotations

import typer
from rich.console import Console
from typer.testing import CliRunner


def test_search_commands_register_adds_typer() -> None:
    """Verify that search commands are registered with the Typer app."""
    from ingenious.cli.search_commands import register_commands

    app = typer.Typer()
    console = Console()
    register_commands(app, console)

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "azure-search" in result.stdout

    # Ensure the run command exists
    result = runner.invoke(app, ["azure-search", "run", "--help"])
    assert result.exit_code == 0
    assert "--search-endpoint" in result.stdout
