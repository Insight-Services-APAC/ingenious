"""Test Azure Search provider constructor and CLI flag handling.

This module contains tests verifying that the `AzureSearchProvider` and the
associated CLI correctly handle the `enable_answer_generation` flag. It ensures
that the provider can override the configuration from settings and that the CLI
properly translates command-line flags and environment variables into the
correct configuration passed to the search pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from typer.testing import CliRunner

from ingenious.services.azure_search import cli as CLI_MOD
from ingenious.services.azure_search.config import SearchConfig
from ingenious.services.azure_search.provider import AzureSearchProvider

if TYPE_CHECKING:
    import pytest
    from click.testing import Result


class DummySettings:
    """Placeholder for IngeniousSettings; the builder stub ignores it."""

    pass


def _stub_pipeline_object() -> Any:
    """Create a minimal stub of the search pipeline object for testing.

    Returns:
        A stub object with `get_answer` and `close` methods.
    """

    class _P:
        async def get_answer(self, q: str) -> dict[str, Any]:
            """Return a minimal response shape expected by the CLI."""
            # Minimal shape expected by the CLI rendering
            return {"answer": "", "source_chunks": []}

        async def close(self) -> None:
            """Provide a no-op close method."""
            return None

    return _P()


def test_provider_constructor_override_true(
    monkeypatch: pytest.MonkeyPatch, config_no_semantic: SearchConfig
) -> None:
    """Verify provider correctly overrides `enable_answer_generation` to True.

    This test ensures that when `AzureSearchProvider` is initialized with
    `enable_answer_generation=True`, this value overrides the one from the
    base configuration loaded from settings.
    """
    captured: dict[str, Any] = {}

    # Builder returns our fixture config
    monkeypatch.setattr(
        "ingenious.services.azure_search.provider.build_search_config_from_settings",
        lambda _settings: config_no_semantic,
    )

    # Capture the cfg that reaches the pipeline factory
    def _capture_config(cfg: SearchConfig) -> Any:
        """Capture the config object passed to the pipeline builder."""
        captured["cfg"] = cfg
        return _stub_pipeline_object()

    monkeypatch.setattr(
        "ingenious.services.azure_search.provider.build_search_pipeline",
        _capture_config,
    )

    # Stub the rerank client used by the provider
    class _Dummy:
        async def close(self) -> None:  # pragma: no cover - trivial
            """Provide a no-op close method for the dummy client."""
            return None

    monkeypatch.setattr(
        "ingenious.services.azure_search.provider.make_async_search_client",
        lambda _cfg: _Dummy(),
    )

    p = AzureSearchProvider(DummySettings(), enable_answer_generation=True)
    assert hasattr(p, "_pipeline")
    assert "cfg" in captured
    assert captured["cfg"].enable_answer_generation is True


def test_provider_constructor_override_none_preserves(
    monkeypatch: pytest.MonkeyPatch, config_no_semantic: SearchConfig
) -> None:
    """Verify provider preserves config value when override is None.

    This test ensures that when `AzureSearchProvider` is initialized with
    `enable_answer_generation=None`, the value from the base configuration
    (which is `False` in the fixture) is preserved.
    """
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        "ingenious.services.azure_search.provider.build_search_config_from_settings",
        lambda _settings: config_no_semantic,
    )

    def _capture_config(cfg: SearchConfig) -> Any:
        """Capture the config object passed to the pipeline builder."""
        captured["cfg"] = cfg
        return _stub_pipeline_object()

    monkeypatch.setattr(
        "ingenious.services.azure_search.provider.build_search_pipeline",
        _capture_config,
    )

    class _Dummy:
        async def close(self) -> None:  # pragma: no cover - trivial
            """Provide a no-op close method for the dummy client."""
            return None

    monkeypatch.setattr(
        "ingenious.services.azure_search.provider.make_async_search_client",
        lambda _cfg: _Dummy(),
    )

    _ = AzureSearchProvider(DummySettings(), enable_answer_generation=None)
    assert captured["cfg"].enable_answer_generation is False


def test_cli_generate_flag_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify the CLI handles the --generate flag and its env var correctly.

    This test checks three scenarios for the `run` subcommand:
    1. Default behavior (no flag): `enable_answer_generation` should be False.
    2. `--generate` flag: `enable_answer_generation` should be True.
    3. `AZURE_SEARCH_ENABLE_GENERATION` env var: `enable_answer_generation`
       should be True.

    It uses a stubbed pipeline builder to capture the `SearchConfig` object
    that the CLI constructs based on the provided arguments and environment.
    A workaround for a Click/Typer parsing quirk is included by placing the
    positional QUERY argument immediately after the subcommand.
    """
    received: list[SearchConfig] = []

    # The pipeline stub we want the CLI to use
    class _StubPipeline:
        async def get_answer(self, q: str) -> dict[str, Any]:
            """Return the minimal shape expected by the CLI runner."""
            return {"answer": "", "source_chunks": []}

        async def close(self) -> None:
            """Provide a no-op close method."""
            pass

    def _shim(cfg: SearchConfig) -> _StubPipeline:
        """Capture the received config and return the stub pipeline."""
        received.append(cfg)
        return _StubPipeline()

    # Patch BOTH the exported shim and the lazy loader used inside the CLI
    monkeypatch.setattr(CLI_MOD, "build_search_pipeline", _shim)
    monkeypatch.setattr(CLI_MOD, "_get_build_pipeline_impl", lambda: _shim)

    runner: CliRunner = CliRunner()

    # Place QUERY ("q") right after 'run' so parsing is unambiguous
    base_args: list[str] = [
        "run",
        "q",
        "--search-endpoint",
        "https://example.search.windows.net",
        "--search-key",
        "sk",
        "--search-index-name",
        "idx",
        "--openai-endpoint",
        "https://example.openai.azure.com",
        "--openai-key",
        "ok",
        "--embedding-deployment",
        "embed",
        "--generation-deployment",
        "gpt",
        "--no-semantic-ranking",
    ]

    # 1) Default (no --generate) => False
    res1: Result = runner.invoke(CLI_MOD.app, base_args)
    assert res1.exit_code == 0, res1.output
    assert received[-1].enable_answer_generation is False

    # 2) With flag => True
    res2: Result = runner.invoke(CLI_MOD.app, base_args + ["--generate"])
    assert res2.exit_code == 0, res2.output
    assert received[-1].enable_answer_generation is True

    # 3) With env var => True (no flag)
    env: dict[str, str] = {"AZURE_SEARCH_ENABLE_GENERATION": "true"}
    res3: Result = runner.invoke(CLI_MOD.app, base_args, env=env)
    assert res3.exit_code == 0, res3.output
    assert received[-1].enable_answer_generation is True
