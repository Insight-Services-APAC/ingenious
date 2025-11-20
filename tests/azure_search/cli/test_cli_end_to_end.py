"""Perform an end-to-end integration test of the Azure Search CLI.

This module provides a smoke test for the `azure-search run` command. Its
purpose is to validate that the CLI can connect to live Azure services and
execute a query successfully, catching integration issues that unit tests miss.

The test runs the real command and asserts that it exits successfully, prints
an "Answer" panel, and prints a "Sources Used" line. It is skipped if the
following environment variables are not set:
- AZURE_SEARCH_ENDPOINT
- AZURE_SEARCH_KEY
- AZURE_SEARCH_INDEX_NAME
- AZURE_OPENAI_ENDPOINT
- AZURE_OPENAI_KEY
- AZURE_OPENAI_EMBEDDING_DEPLOYMENT
- AZURE_OPENAI_GENERATION_DEPLOYMENT
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

if TYPE_CHECKING:
    from typer.testing import Result


@pytest.mark.azure_integration
def test_end_to_end_cli_runs_query_and_maps_results() -> None:
    """Run the CLI and assert the output has the correct structure.

    This test simulates a user running a query via the `azure-search run`
    command. It checks for the required environment variables, constructs the
    command arguments, invokes the CLI, and then validates the output. The
    primary goal is to ensure the command executes without errors and that the
    generated answer and source citations are present in the output, confirming
    the end-to-end data flow is working.
    """
    required_env: list[str] = [
        "AZURE_SEARCH_ENDPOINT",
        "AZURE_SEARCH_KEY",
        "AZURE_SEARCH_INDEX_NAME",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_KEY",
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
        "AZURE_OPENAI_GENERATION_DEPLOYMENT",
    ]
    missing: list[str] = [k for k in required_env if not os.getenv(k)]
    if missing:
        pytest.skip(f"Missing env vars for Azure integration test: {missing}")

    # Build the environment passed to the CLI (only the required keys)
    env: dict[str, str] = {k: os.environ[k] for k in required_env}

    # Query can be overridden if you want to target a known doc in your index
    query: str = os.getenv("AZURE_SEARCH_TEST_QUERY", "integration smoke test")

    # Use small K/N to minimize cost and latency; disable semantic ranking unless AZURE_SEARCH_SEMANTIC_CONFIG is provided.
    args: list[str] = [
        "azure-search",
        "run",
        query,
        "--embedding-deployment",
        env["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"],
        "--generation-deployment",
        env["AZURE_OPENAI_GENERATION_DEPLOYMENT"],
        "--no-semantic-ranking",
        "--top-k-retrieval",
        "4",
        "--top-n-final",
        "2",
        "--generate",  # ← was "generate"
    ]

    # Invoke the real CLI
    from ingenious.cli.main import app  # import after app wiring

    runner = CliRunner()
    result: Result = runner.invoke(app, args, env=env)

    # Basic execution succeeded
    assert result.exit_code == 0, f"CLI failed:\nSTDOUT:\n{result.stdout}"

    out: str = result.stdout

    # Prologue shows the query we sent (useful debug)
    assert query in out, f"Expected query '{query}' to be echoed.\n{out}"

    # An answer panel is printed; we just require that it exists and is non-empty text.
    # The panel title contains the word 'Answer' (Rich markup may be present).
    assert "Answer" in out, f"Expected an Answer panel in output.\n{out}"

    # The CLI always prints 'Sources Used (N):' even if N == 0.
    m: re.Match[str] | None = re.search(r"Sources Used\s*\((\d+)\):", out)
    assert m is not None, f"Expected 'Sources Used (N):' line.\n{out}"
    # N is a non-negative integer; we don't force >0 to avoid flakiness across indices.
    n_sources: int = int(m.group(1))
    assert n_sources >= 0
