"""Test the `azure-search` CLI command routing and configuration building.

This module contains integration tests for the `azure-search` command group
in the main CLI application. It verifies that command-line arguments and
environment variables are correctly parsed and passed to the underlying
service-layer functions. It focuses on the "glue" code rather than the
business logic of the search pipeline itself, which is tested elsewhere.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from typer.testing import CliRunner

if TYPE_CHECKING:
    from pytest import MonkeyPatch

CLI_MOD = "ingenious.services.azure_search.cli"


def test_azure_search_run_routes_and_builds_config(monkeypatch: MonkeyPatch) -> None:
    """Verify `azure-search run` correctly builds config and calls the pipeline.

    This test ensures that the Typer command correctly gathers configuration
    from both environment variables (for secrets and endpoints) and command-line
    arguments (for operational parameters), constructs the `SearchConfig`
    pydantic model, and invokes the underlying `_run_search_pipeline` function
    with the expected arguments.
    """
    from ingenious.cli.main import app  # imports must occur after code wiring

    runner: CliRunner = CliRunner()

    env: dict[str, str] = {
        "AZURE_SEARCH_ENDPOINT": "https://x.search.windows.net",
        "AZURE_SEARCH_KEY": "sk",
        "AZURE_SEARCH_INDEX_NAME": "idx",
        "AZURE_OPENAI_ENDPOINT": "https://oai.example.com",
        "AZURE_OPENAI_KEY": "ok",
        "AZURE_SEARCH_SEMANTIC_CONFIG": "default-sem",
    }

    # We must still pass deployments to avoid prompts.
    args: list[str] = [
        "azure-search",
        "run",
        "hello world",
        "--embedding-deployment",
        "embed-depl",
        "--generation-deployment",
        "gen-depl",
        "--top-k-retrieval",
        "7",
        "--top-n-final",
        "3",
        "--verbose",
    ]

    with (
        patch(f"{CLI_MOD}._run_search_pipeline") as mock_run,
        patch(f"{CLI_MOD}.setup_logging") as mock_setup,
    ):
        result = runner.invoke(app, args, env=env)

    assert result.exit_code == 0
    mock_setup.assert_called_once_with(True)

    # Validate the config object and args that were passed to the internal runner
    (config_arg, query_arg, verbose_arg), _ = mock_run.call_args
    assert query_arg == "hello world"
    assert verbose_arg is True

    # The config is a pydantic model from the Azure Search module
    from ingenious.services.azure_search.config import SearchConfig

    assert isinstance(config_arg, SearchConfig)
    assert config_arg.search_endpoint == env["AZURE_SEARCH_ENDPOINT"]
    assert config_arg.search_key.get_secret_value() == env["AZURE_SEARCH_KEY"]
    assert config_arg.search_index_name == env["AZURE_SEARCH_INDEX_NAME"]
    assert config_arg.openai_endpoint == env["AZURE_OPENAI_ENDPOINT"]
    assert config_arg.openai_key.get_secret_value() == env["AZURE_OPENAI_KEY"]
    assert config_arg.semantic_configuration_name == env["AZURE_SEARCH_SEMANTIC_CONFIG"]
    assert config_arg.embedding_deployment_name == "embed-depl"
    assert config_arg.generation_deployment_name == "gen-depl"
    assert config_arg.top_k_retrieval == 7
    assert config_arg.top_n_final == 3
