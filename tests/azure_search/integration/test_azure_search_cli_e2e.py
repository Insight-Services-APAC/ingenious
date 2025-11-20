"""Run end-to-end tests for the Azure Search CLI pipeline.

This module verifies that the CLI command `azure-search run` can execute
a full pipeline, connecting to live Azure services. These tests are marked
for integration testing and require specific environment variables to be
set for authentication and configuration with Azure Search and Azure OpenAI.
They are skipped if the required environment variables are not found.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

if TYPE_CHECKING:
    from click.testing import Result


REQUIRED_ENV: list[str] = [
    "AZURE_SEARCH_ENDPOINT",
    "AZURE_SEARCH_KEY",
    "AZURE_SEARCH_INDEX_NAME",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_KEY",
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
    "AZURE_OPENAI_GENERATION_DEPLOYMENT",
]


def _have_env() -> bool:
    """Check if all required Azure environment variables are set.

    This function is used by pytest.mark.skipif to conditionally
    skip tests that depend on a live Azure environment.
    """
    return all(os.getenv(k) for k in REQUIRED_ENV)


@pytest.mark.azure_integration
@pytest.mark.skipif(not _have_env(), reason="Azure integration env vars not set")
def test_cli_e2e_runs_pipeline_and_prints_status() -> None:
    """Verify the 'azure-search run' CLI command executes and prints status.

    This end-to-end test invokes the main CLI application, simulating a user
    running the command. It checks for a successful exit code and verifies that
    expected status messages are present in the output, confirming the pipeline
    started execution.
    """
    from ingenious.cli.main import app

    # Remove mix_stderr parameter - not supported in newer versions
    runner = CliRunner()

    res: Result = runner.invoke(app, ["azure-search", "run", "sanity question"])
    assert res.exit_code == 0, (res.stdout or "") + (res.stderr or "")
    # A couple of tolerant status markers; change to your actual phrasing if you prefer
    combined: str = (res.stdout or "") + (res.stderr or "")
    assert ("Executing Advanced Search Pipeline" in combined) or (
        "Starting search for:" in combined
    )
