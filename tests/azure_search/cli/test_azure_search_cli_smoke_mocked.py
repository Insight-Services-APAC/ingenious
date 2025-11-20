"""Smoke tests for the Azure Search CLI end-to-end functionality.

This module verifies that the `azure-search run` command-line interface
can be invoked successfully with the required environment variables and
arguments. It uses mocks to avoid actual network calls to Azure services,
focusing solely on the CLI entry point and argument parsing logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from typer.testing import CliRunner

if TYPE_CHECKING:
    from typer.testing import Result


def test_azure_search_run_smoke_success() -> None:
    """Test that the 'azure-search run' command executes successfully.

    This smoke test ensures the CLI command can be invoked with all necessary
    options and environment variables, triggering the underlying search
    pipeline logic without errors.
    """
    from ingenious.cli.main import app

    runner: CliRunner = CliRunner()
    env: dict[str, str] = {
        "AZURE_SEARCH_ENDPOINT": "https://s",
        "AZURE_SEARCH_KEY": "k",
        "AZURE_SEARCH_INDEX_NAME": "i",
        "AZURE_OPENAI_ENDPOINT": "https://oai",
        "AZURE_OPENAI_KEY": "ok",
    }
    args: list[str] = [
        "azure-search",
        "run",
        "q",
        "--embedding-deployment",
        "emb",
        "--generation-deployment",
        "gen",
        # FIX: Use the correct CLI argument name '--semantic-config'.
        "--semantic-config",
        "test-config",
    ]
    with patch("ingenious.services.azure_search.cli._run_search_pipeline") as mock_run:
        result: Result = runner.invoke(app, args, env=env)
    assert result.exit_code == 0
    # The CLI prints a “Starting search for” line; we can assert it’s present
    assert "Starting search for: '[bold]q[/bold]'" in result.stdout
    mock_run.assert_called_once()
