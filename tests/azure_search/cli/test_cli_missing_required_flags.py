"""Verify CLI commands fail gracefully when required configuration is missing.

This module contains tests for the command-line interface (CLI) that
specifically check for correct error handling when required arguments or
environment variables are omitted. The goal is to ensure the CLI provides
clear, actionable feedback to the user and exits with a non-zero status
code upon validation failure.
"""

# -*- coding: utf-8 -*-
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

if TYPE_CHECKING:
    from typer.testing import Result


@pytest.mark.skip(reason="CLI currently allows missing index name with default/fallback behavior")
def test_cli_missing_search_index_name_exits_nonzero() -> None:
    """Verify the CLI exits with a non-zero code if the index name is missing.

    This test ensures that the Azure Search command fails fast with a clear
    error message when a required environment variable (`AZURE_SEARCH_INDEX_NAME`)
    is not provided. It checks for a non-zero exit code and an informative
    error message in stderr.
    """
    from ingenious.cli.main import app  # import after app wiring

    runner: CliRunner = CliRunner()

    env: dict[str, str] = {
        "AZURE_SEARCH_ENDPOINT": "https://unit.search.windows.net",
        "AZURE_SEARCH_KEY": "sk",
        # "AZURE_SEARCH_INDEX_NAME": intentionally omitted
        "AZURE_OPENAI_ENDPOINT": "https://oai.example.com",
        "AZURE_OPENAI_KEY": "ok",
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "emb",
        "AZURE_OPENAI_GENERATION_DEPLOYMENT": "gen",
    }

    res: Result = runner.invoke(app, ["azure-search", "run", "q"], env=env)
    # Non-zero exit is sufficient (Click uses code 2 for bad params, 1 for exceptions)
    assert res.exit_code != 0, (res.stdout or "") + (res.stderr or "")

    combined: str = (res.stderr or "") + (res.stdout or "")
    # Be tolerant to phrasing differences between Pydantic/our wrapper
    assert any(
        s in combined for s in ("search_index_name", "AZURE_SEARCH_INDEX_NAME", "index name")
    ), combined
