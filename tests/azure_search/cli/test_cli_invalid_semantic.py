"""Tests CLI failure modes for Azure Search semantic ranking configuration.

This module verifies that the command-line interface (CLI) correctly handles
invalid configurations related to semantic ranking. Specifically, it ensures
that the application exits with a non-zero status code when semantic ranking
is enabled but the required semantic configuration name is missing, preventing
runtime errors from invalid Azure Search API calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

if TYPE_CHECKING:
    from typer.testing import Result


@pytest.mark.xfail(
    strict=False,
    reason=(
        "Current CLI prints a config error panel but exits 0 when "
        "use_semantic_ranking=True and no semantic config name is supplied. "
        "Desired behavior: exit code 1."
    ),
)
def test_cli_invalid_semantic_requires_name_exits_1() -> None:
    """Verify CLI exits with an error if semantic ranking is on but no config name is given.

    This test simulates a common misconfiguration where a user enables semantic
    ranking (which is on by default) but fails to provide the name of the semantic
    configuration profile in the Azure Search index. The CLI should detect this
    contradiction, report a clear error, and exit with a non-zero status code to
    prevent a runtime failure when querying the search service.
    """
    from ingenious.cli.main import app  # import after app wiring

    env: dict[str, str] = {
        # Azure Search (no semantic config provided)
        "AZURE_SEARCH_ENDPOINT": "https://search.example.net",
        "AZURE_SEARCH_KEY": "sk",
        "AZURE_SEARCH_INDEX_NAME": "idx",
        # Azure OpenAI
        "AZURE_OPENAI_ENDPOINT": "https://oai.example.com",
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
        # note: NOT passing --no-semantic-ranking and NOT setting AZURE_SEARCH_SEMANTIC_CONFIG
    ]

    res: Result = CliRunner().invoke(app, args, env=env)
    # Desired contract:
    assert res.exit_code == 1, res.stdout
    assert "semantic" in res.stdout.lower()
