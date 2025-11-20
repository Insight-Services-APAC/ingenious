"""Ensures CLI commands are not mounted multiple times.

This module contains regression tests to verify that CLI commands, specifically
those added via Typer/Click mounting, do not appear more than once in the
`--help` output. This can happen if the mounting logic is flawed or if
imports cause the mounting code to run multiple times.
"""

from typing import TYPE_CHECKING

from typer.testing import CliRunner

if TYPE_CHECKING:
    from click.testing import Result


def test_azure_search_appears_once_in_help() -> None:
    """Verify 'azure-search' command appears only once in help output.

    This is a regression test to prevent a bug where the `azure-search` Typer
    app was being mounted multiple times, causing it to show up repeatedly
    in the main application's help text.
    """
    from ingenious.cli.main import app

    runner: CliRunner = CliRunner()
    res: Result = runner.invoke(app, ["--help"])
    assert res.exit_code == 0
    count: int = res.stdout.count("azure-search")
    assert count == 1, f"azure-search appears {count} times in help:\n{res.stdout}"
