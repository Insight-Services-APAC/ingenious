"""Tests the behavior of the Azure Search CLI command.
This module contains integration-style tests for the command-line interface
of the Azure Search service. It focuses on validating the CLI's direct
responsibilities, such as argument parsing, error handling, and environment
setup (like logging), rather than the full search pipeline execution.
These tests mock the underlying pipeline to remain fast and offline.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import patch

from typer.testing import CliRunner

if TYPE_CHECKING:
    from click.testing import Result


def _base_env() -> dict[str, str]:
    """Provide minimal environment variables for SearchConfig validation."""
    # This ensures that the configuration loading part of the CLI passes,
    # allowing tests to focus on the CLI's own logic and error handling.
    return {
        "AZURE_SEARCH_ENDPOINT": "https://search.example.net",
        "AZURE_SEARCH_KEY": "search-key",
        "AZURE_SEARCH_INDEX_NAME": "my-index",
        "AZURE_OPENAI_ENDPOINT": "https://aoai.example.com",
        "AZURE_OPENAI_KEY": "openai-key",
    }


# FIX: Update _base_args to use the correct argument name --semantic-config.
def _base_args(
    verbose: bool = False, include_semantic_config: bool = True
) -> list[str]:
    """Create a base list of command-line arguments for the 'run' command."""
    # This helper provides a consistent set of arguments for invoking the CLI,
    # making tests easier to read and maintain.
    args: list[str] = [
        "azure-search",
        "run",
        "test query",
        "--embedding-deployment",
        "emb-deploy",
        "--generation-deployment",
        "gen-deploy",
        "--semantic-ranking",  # explicit ON (it's True by default, but be clear)
    ]
    if include_semantic_config:
        # Use the correct argument name recognized by the CLI
        args.extend(["--semantic-config", "test-config"])

    if verbose:
        args.append("--verbose")
    return args


def test_cli_missing_semantic_name_exits_1() -> None:
    """Verify CLI exits with code 1 if semantic config name is missing."""
    # With --semantic-ranking enabled and no --semantic-config, the CLI
    # validation should trigger. This test ensures the CLI catches this
    # specific configuration error and provides a clear message to the user before
    # exiting with a non-zero status code.
    # Import root app only after the CLI tree has registered subcommands
    from ingenious.cli.main import app

    # The validation is now handled by the CLI directly.
    # We invoke the CLI explicitly excluding the semantic config.
    result: Result = CliRunner().invoke(
        app, _base_args(include_semantic_config=False), env=_base_env()
    )

    assert result.exit_code == 1
    # The CLI prints a specific error message for this validation failure
    assert (
        "Error: Semantic ranking is enabled but no semantic configuration name was provided."
        in result.stdout
    )
    assert (
        "Supply --semantic-config or set AZURE_SEARCH_SEMANTIC_CONFIG." in result.stdout
    )


def test_cli_verbose_sets_component_loggers() -> None:
    """Verify --verbose flag sets component loggers to DEBUG level."""
    # The CLI is responsible for configuring logging verbosity. This test
    # confirms that passing the --verbose flag correctly cascades the DEBUG
    # log level to all relevant sub-component loggers, aiding in debugging.
    # The actual pipeline execution is patched to isolate the logging setup logic.
    from ingenious.cli.main import app

    # Bring the CLI module in to access its __name__ for the logger list
    from ingenious.services.azure_search import (
        cli as az_cli,
    )

    # These are the logger names the CLI configures in setup_logging(verbose)
    logger_names: list[str] = [
        "ingenious.services.azure_search.pipeline",
        "ingenious.services.azure_search.components.retrieval",
        "ingenious.services.azure_search.components.fusion",
        "ingenious.services.azure_search.components.generation",
        az_cli.__name__,  # CLI module logger itself
    ]
    # Start from a clean, non-DEBUG state to prove the effect
    for name in logger_names:
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger().setLevel(logging.WARNING)
    # Avoid running the real pipeline; we only want logging setup from CLI
    # Use _base_args(verbose=True), which now includes the correct semantic config argument by default.
    with patch(
        "ingenious.services.azure_search.cli._run_search_pipeline", return_value=None
    ):
        result: Result = CliRunner().invoke(
            app, _base_args(verbose=True), env=_base_env()
        )
    assert result.exit_code == 0
    # All component loggers should now be DEBUG
    for name in logger_names:
        assert logging.getLogger(name).level == logging.DEBUG, f"{name} not DEBUG"
    # Root logger should also be DEBUG when --verbose is used
    assert logging.getLogger().level == logging.DEBUG
