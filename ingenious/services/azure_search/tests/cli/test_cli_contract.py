"""Tests for Azure Search CLI command error handling.

This module contains tests for the `ingenious.services.azure_search.cli` module,
specifically focusing on verifying that configuration and runtime errors within
the search pipeline are caught and result in a non-zero exit code. It ensures
the command-line interface provides clear failure feedback to the user or
calling scripts instead of failing silently.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NoReturn

import pytest
import typer

from ingenious.services.azure_search import cli

if TYPE_CHECKING:
    from pytest import MonkeyPatch


def test_cli_semantic_enabled_without_name_exits_1(
    config: Any, monkeypatch: MonkeyPatch
) -> None:
    """Verify ValueError in pipeline build exits with code 1.

    This test ensures that when the pipeline factory `build_search_pipeline`
    raises a `ValueError` (e.g., due to a misconfiguration), the main CLI
    runner function `_run_search_pipeline` catches it and properly exits with
    a non-zero status code, preventing silent failures.
    """

    def raise_value_error(*_a: Any, **_k: Any) -> NoReturn:
        """Raise a ValueError to simulate a configuration error during pipeline build."""
        raise ValueError(
            "semantic ranking is enabled but semantic config name is missing"
        )

    # Make the factory blow up; no need to construct a special config since we force the error.
    monkeypatch.setattr(cli, "build_search_pipeline", raise_value_error, raising=False)

    with pytest.raises(typer.Exit) as ei:
        # NOTE: correct signature is (config, query, verbose)
        cli._run_search_pipeline(config, "hello world", False)

    assert ei.value.exit_code == 1
