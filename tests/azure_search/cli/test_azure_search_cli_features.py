"""Tests specific feature flags and behaviors for the Azure Search CLI.

This module contains integration tests for the Azure Search command-line
interface, focusing on validating specific command-line arguments and their
effect on the application's configuration and behavior. It uses Typer's
CliRunner to invoke the CLI and mocks the core pipeline logic to isolate
the CLI argument parsing and configuration setup.
The main entry point tested is the `app` object from the `cli` module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner, Result

# Assuming 'app' is correctly imported from the CLI definition module
# If the structure is different, the import path might need adjustment.
# Based on previous context, this import seems correct:
from ingenious.services.azure_search.cli import app

if TYPE_CHECKING:
    from pathlib import Path
runner: CliRunner = CliRunner()
BASE_ARGS: list[str] = [
    "run",
    "--search-endpoint",
    "https://cli.search.windows.net",
    "--search-key",
    "cli-search-key",
    # FIX: Add the required search index name to pass SearchConfig validation.
    "--search-index-name",
    "test-index",
    "--openai-endpoint",
    "https://cli.openai.azure.com",
    "--openai-key",
    "cli-openai-key",
    "--embedding-deployment",
    "cli-embed",
    "--generation-deployment",
    "cli-gen",
    # Use the correct CLI argument name '--semantic-config'.
    "--semantic-config",
    "test-config",
]


def test_azure_search_cli_load_custom_dat_prompt_file_success(
    tmp_path: Path,
) -> None:
    """Verify the CLI correctly loads a custom DAT prompt from a specified file.

    This test ensures that when the `--dat-prompt-file` argument is used
    with a valid file path, the contents of that file are correctly read
    and passed into the application's configuration.
    """
    prompt_content: str = "Custom DAT prompt content."
    prompt_file: Path = tmp_path / "custom_prompt.txt"
    prompt_file.write_text(prompt_content)
    # NOTE: flags BEFORE the query; query LAST and after `--`
    args: list[str] = BASE_ARGS + [
        "--dat-prompt-file",
        str(prompt_file),
        "--",
        "test query",
    ]
    mock_run_pipeline = MagicMock()
    with patch("ingenious.services.azure_search.cli._run_search_pipeline", mock_run_pipeline):
        # When invoking the app directly imported from the specific CLI module,
        # we don't need the top-level command prefix (e.g., 'azure-search').
        result: Result = runner.invoke(app, args)
    assert result.exit_code == 0, f"CLI exited with error: {result.output}"
    # The first positional argument passed to the mocked function is the config object.
    # Ensure the mock was called before accessing call_args
    assert mock_run_pipeline.called, "Pipeline run function was not called."
    config_arg: Any = mock_run_pipeline.call_args[0][0]
    assert config_arg.dat_prompt == prompt_content


def test_azure_search_cli_load_custom_dat_prompt_file_not_found() -> None:
    """Verify the CLI exits gracefully if the DAT prompt file is not found.

    This test ensures that if the path provided to `--dat-prompt-file`
    does not exist, the CLI exits with a non-zero status code and prints
    an informative error message, without attempting to run the main pipeline.
    """
    # NOTE: flags BEFORE the query; query LAST and after `--`
    args: list[str] = BASE_ARGS + [
        "--dat-prompt-file",
        "/non/existent/file.txt",
        "--",
        "test query",
    ]
    mock_run_pipeline = MagicMock()
    with patch("ingenious.services.azure_search.cli._run_search_pipeline", mock_run_pipeline):
        result: Result = runner.invoke(app, args)

    # Check stdout and stderr as CLI tools often print errors to stderr
    output = result.stdout + result.stderr
    assert result.exit_code != 0
    # Ensure the error message matches the expected output for file not found
    assert "Error: DAT prompt file not found" in output
    mock_run_pipeline.assert_not_called()
