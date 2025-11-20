# -- coding: utf-8 --
"""Provide tests for the Azure Search CLI module.

This module contains unit and integration tests for the command-line interface
(CLI) defined in `ingenious.services.azure_search.cli`. It verifies the correct
handling of command-line arguments, environment variables, logging setup, and
the orchestration of the search pipeline.

Tests cover success paths, configuration errors (e.g., bad factory input),
runtime exceptions during pipeline execution, and file I/O for custom prompts.
The primary entry points under test are the `run` command and its underlying
helper functions `setup_logging` and `_run_search_pipeline`.
"""

from __future__ import annotations

import logging
from contextlib import AbstractContextManager
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner, Result

from ingenious.services.azure_search.cli import _run_search_pipeline, app, setup_logging
from ingenious.services.azure_search.config import DEFAULT_DAT_PROMPT, SearchConfig

if TYPE_CHECKING:
    from pytest import CaptureFixture

runner: CliRunner = CliRunner()
CLI_MOD: str = "ingenious.services.azure_search.cli"


def test_setup_logging_verbose() -> None:
    """Test that verbose logging sets the log level to DEBUG."""
    with patch("logging.getLogger") as gl:
        lg: MagicMock = MagicMock()
        gl.return_value = lg
        setup_logging(verbose=True)
        # root called once at end w/o name
        assert lg.setLevel.called
        for call in lg.setLevel.call_args_list:
            assert call.args[0] == logging.DEBUG


def test_setup_logging_non_verbose() -> None:
    """Test that non-verbose logging sets the log level to INFO."""
    with patch("logging.getLogger") as gl:
        lg: MagicMock = MagicMock()
        gl.return_value = lg
        setup_logging(verbose=False)
        for call in lg.setLevel.call_args_list:
            assert call.args[0] == logging.INFO


def _patch_build_pipeline(mock_instance: MagicMock) -> AbstractContextManager[Any]:
    """Create a patch for the search pipeline builder.

    This is a test helper to simplify mocking the `build_search_pipeline`
    factory function within different test scenarios.
    """
    return patch(f"{CLI_MOD}.build_search_pipeline", mock_instance)


def test_run_search_pipeline_success(config: SearchConfig, capsys: CaptureFixture[str]) -> None:
    """Test the successful execution of the search pipeline.

    This test verifies that when the pipeline runs without errors, it prints the
    expected answer and source panels to stdout and properly closes the
    pipeline resources asynchronously.
    """
    mock_pipe: MagicMock = MagicMock()
    mock_pipe.get_answer = AsyncMock(
        return_value={
            "answer": "A",
            "source_chunks": [
                {
                    "id": "S",
                    "content": "X" * 400,
                    "_final_score": 3.51234,
                    "_retrieval_type": "hyb",
                }
            ],
        }
    )
    mock_pipe.close = AsyncMock()
    with _patch_build_pipeline(MagicMock(return_value=mock_pipe)):
        _run_search_pipeline(config, "q", verbose=False)
    out: str = capsys.readouterr().out
    assert "Executing Advanced Search Pipeline" in out
    assert "Answer" in out or "A" in out
    assert "Sources Used (1)" in out
    assert "3.5123" in out  # rounded
    mock_pipe.close.assert_awaited()


def test_run_search_pipeline_config_error(
    config: SearchConfig, capsys: CaptureFixture[str]
) -> None:
    """Test that a pipeline build error causes a graceful exit.

    This test ensures that if `build_search_pipeline` raises a `ValueError`
    (e.g., due to invalid configuration), the CLI wrapper function catches it,
    prints a user-friendly error message, and exits with a status code of 1.
    """
    with _patch_build_pipeline(MagicMock(side_effect=ValueError("bad sem"))):
        # New contract: _run_search_pipeline must exit(1) on config errors
        with pytest.raises(typer.Exit) as ei:
            _run_search_pipeline(config, "q", verbose=False)
    assert ei.value.exit_code == 1
    out: str = capsys.readouterr().out
    assert "Configuration failed: bad sem" in out


def test_run_search_pipeline_runtime_error_verbose(config: SearchConfig) -> None:
    """Test that a runtime error in verbose mode prints a traceback.

    This test verifies that if the pipeline's `get_answer` method raises an
    exception, the CLI runner will print a full exception traceback to the
    console when the `--verbose` flag is active.
    """
    mock_pipe: MagicMock = MagicMock()
    mock_pipe.get_answer = AsyncMock(side_effect=RuntimeError("boom"))
    mock_pipe.close = AsyncMock()
    with (
        _patch_build_pipeline(MagicMock(return_value=mock_pipe)),
        patch(f"{CLI_MOD}.console.print_exception") as pe,
    ):
        _run_search_pipeline(config, "q", verbose=True)
        pe.assert_called_once()


ENV: dict[str, str] = {
    "AZURE_SEARCH_ENDPOINT": "https://s",
    "AZURE_SEARCH_KEY": "sk",
    "AZURE_SEARCH_INDEX_NAME": "idx",
    "AZURE_OPENAI_ENDPOINT": "https://o",
    "AZURE_OPENAI_KEY": "ok",
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "emb",
    "AZURE_OPENAI_GENERATION_DEPLOYMENT": "gen",
    "AZURE_SEARCH_SEMANTIC_CONFIG": "sem",
}


def test_cli_run_env_parsing(tmp_path: Path) -> None:
    """Test that the CLI correctly parses configuration from environment variables.

    This ensures that when the CLI is invoked, it correctly constructs a
    `SearchConfig` object using default values sourced from environment variables,
    without any command-line overrides.
    """
    with (
        patch(f"{CLI_MOD}._run_search_pipeline") as rp,
        patch(f"{CLI_MOD}.setup_logging") as sl,
    ):
        res: Result = runner.invoke(app, ["what?"], env=ENV)
        assert res.exit_code == 0
        sl.assert_called_once_with(False)
        cfg: SearchConfig
        q: str
        verbose: bool
        (cfg, q, verbose) = rp.call_args[0]
        assert isinstance(cfg, SearchConfig)
        assert q == "what?"
        assert verbose is False
        assert cfg.semantic_configuration_name == "sem"
        assert cfg.dat_prompt == DEFAULT_DAT_PROMPT


def test_cli_run_options_override(tmp_path: Path) -> None:
    """Test that command-line options override environment variables.

    This test verifies that configuration values provided via explicit CLI flags
    (like `--top-k-retrieval` or `--no-semantic-ranking`) take precedence over
    the values set in the environment.
    """
    with (
        patch(f"{CLI_MOD}._run_search_pipeline") as rp,
        patch(f"{CLI_MOD}.setup_logging"),
    ):
        res: Result = runner.invoke(
            app,
            [
                "q",
                "--top-k-retrieval",
                "50",
                "--top-n-final",
                "10",
                "--no-semantic-ranking",
                "--verbose",
                "--search-endpoint",
                "https://override",
            ],
            env=ENV,
        )
        assert res.exit_code == 0
        cfg: SearchConfig = rp.call_args[0][0]
        assert cfg.top_k_retrieval == 50
        assert cfg.top_n_final == 10
        assert cfg.use_semantic_ranking is False
        assert cfg.search_endpoint == "https://override"


def test_cli_custom_dat_prompt_success(tmp_path: Path) -> None:
    """Test loading a custom DAT prompt from a file.

    This ensures the `--dat-prompt-file` option correctly reads the content of
    the specified file and uses it to configure the search pipeline.
    """
    p: Path = tmp_path / "dat.txt"
    p.write_text("CUSTOM")
    with patch(f"{CLI_MOD}._run_search_pipeline") as rp:
        res: Result = runner.invoke(app, ["q", "--dat-prompt-file", str(p)], env=ENV)
        assert res.exit_code == 0
        assert rp.call_args[0][0].dat_prompt == "CUSTOM"


def test_cli_custom_dat_prompt_missing() -> None:
    """Test that a missing prompt file causes the CLI to exit with an error.

    This verifies that if the file specified by `--dat-prompt-file` does not
    exist, the CLI prints an error message and exits with a non-zero status
    code without attempting to run the search pipeline.
    """
    with patch(f"{CLI_MOD}._run_search_pipeline") as rp:
        res: Result = runner.invoke(app, ["q", "--dat-prompt-file", "missing.txt"], env=ENV)
        assert res.exit_code == 1
        assert "DAT prompt file not found" in res.stdout
        rp.assert_not_called()
