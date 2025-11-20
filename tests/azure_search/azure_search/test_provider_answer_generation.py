"""Tests for the answer generation feature of the AzureSearchProvider.

This module verifies the behavior of the `answer` method, particularly its
pre-flight check that disables the functionality when not explicitly enabled.
It ensures that the provider correctly raises a `GenerationDisabledError`
when answer generation is turned off, preventing unintended calls to the
underlying search pipeline. Tests also confirm that the `retrieve` method
remains unaffected by this setting.

The primary entry points under test are the `AzureSearchProvider.answer` and
`AzureSearchProvider.retrieve` methods. Stubs and fixtures are used to
isolate provider logic from actual Azure services.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    pass


@pytest.mark.asyncio
async def test_answer_raises_when_generation_disabled(
    import_provider_with_stubs: Any, settings_disabled: Any
) -> None:
    """Verify `answer` raises GenerationDisabledError when the feature is off.

    This test ensures that when answer generation is disabled by default in the
    settings, calling the `answer` method triggers a specific pre-flight error
    before attempting to execute the search pipeline.
    """
    provider_mod = import_provider_with_stubs
    Provider = provider_mod.AzureSearchProvider
    from ingenious.services.retrieval.errors import (
        GenerationDisabledError,
        PreflightError,
    )

    prov = Provider(settings_disabled)  # default: generation disabled
    with pytest.raises(GenerationDisabledError) as excinfo:
        await prov.answer("what is dat fusion?")
    # Subclass check / back-compat
    assert isinstance(excinfo.value, PreflightError)
    # Reason & snapshot available
    assert (
        getattr(excinfo.value, "reason", "") == "generation_disabled"
        or getattr(getattr(excinfo.value, "reason", ""), "value", "") == "generation_disabled"
    )
    snap: dict[str, Any] = getattr(excinfo.value, "snapshot", {})
    assert "use_semantic_ranking" in snap and "top_n_final" in snap

    # Ensure fail-fast: pipeline.get_answer was NOT called
    dummy_pipeline = provider_mod.build_search_pipeline(None)  # returns the shared dummy
    assert dummy_pipeline.get_answer_called == 0


@pytest.mark.asyncio
async def test_answer_succeeds_when_generation_enabled(
    import_provider_with_stubs: Any, settings_disabled: Any
) -> None:
    """Verify `answer` succeeds when explicitly enabled via constructor override.

    This test confirms that passing `enable_answer_generation=True` to the provider's
    constructor successfully overrides the disabled-by-default setting and allows
    the `answer` method to execute as expected.
    """
    provider_mod = import_provider_with_stubs
    Provider = provider_mod.AzureSearchProvider

    # Explicit override should enable generation, regardless of settings default.
    prov = Provider(settings_disabled, enable_answer_generation=True)
    res: dict[str, Any] = await prov.answer("q")
    assert isinstance(res, dict)
    assert res["answer"] == "A"
    assert res["source_chunks"] and res["source_chunks"][0]["id"] == "1"

    # Sanity: pipeline.get_answer called exactly once
    dummy_pipeline = provider_mod.build_search_pipeline(None)
    assert dummy_pipeline.get_answer_called == 1


@pytest.mark.asyncio
async def test_constructor_override_false_is_respected(
    import_provider_with_stubs: Any, settings_enabled: Any
) -> None:
    """Verify constructor override `enable_answer_generation=False` is respected.

    This test ensures that if the settings would otherwise enable generation,
    an explicit `False` passed to the constructor correctly disables it,
    upholding the override's precedence.
    """
    provider_mod = import_provider_with_stubs
    Provider = provider_mod.AzureSearchProvider
    from ingenious.services.retrieval.errors import GenerationDisabledError

    # settings_enabled doesn't actually flip the SearchConfig;
    # but ctor override False must be respected if provided.
    prov = Provider(settings_enabled, enable_answer_generation=False)
    with pytest.raises(GenerationDisabledError):
        await prov.answer("q")


@pytest.mark.asyncio
async def test_preflight_superclass_still_catches(
    import_provider_with_stubs: Any, settings_disabled: Any
) -> None:
    """Verify `GenerationDisabledError` can be caught via its `PreflightError` superclass.

    This ensures that client code can use a broader exception handler for any
    pre-flight validation failures, maintaining backward compatibility and
    flexible error handling strategies.
    """
    provider_mod = import_provider_with_stubs
    Provider = provider_mod.AzureSearchProvider
    from ingenious.services.retrieval.errors import PreflightError

    prov = Provider(settings_disabled)
    with pytest.raises(PreflightError):
        await prov.answer("q")


@pytest.mark.asyncio
async def test_public_reexport_path_optional(import_provider_with_stubs: Any) -> None:
    """Test that `GenerationDisabledError` is optionally re-exported from the package root.

    This is a convenience test. It checks if the specific error type is made
    available at `ingenious.services.azure_search` for easier importing by clients,
    skipping if the re-export does not exist.
    """
    try:
        from ingenious.services.azure_search import GenerationDisabledError  # re-export

        assert issubclass(GenerationDisabledError, Exception)
    except ImportError:
        pytest.skip("GenerationDisabledError not re-exported at package root.")


class _DummyPipeline:
    """Minimal pipeline exposing only retrieve + close."""

    async def retrieve(self, *_: Any, **__: Any) -> list[dict[str, Any]]:
        """Return a canned result to prove delegation."""
        return [{"id": "1", "content": "ok"}]

    async def close(self) -> None:
        """No-op."""
        return None


@pytest.mark.asyncio
async def test_retrieve_unaffected_when_generation_disabled(
    import_provider_with_stubs: Any, settings_disabled: Any
) -> None:
    """Ensure provider.retrieve delegates to pipeline.retrieve without touching generation flags."""
    provider_mod = import_provider_with_stubs
    p = _DummyPipeline()
    prov = provider_mod.AzureSearchProvider(settings_or_config=settings_disabled, pipeline=p)
    rows = await prov.retrieve("q")
    assert rows and rows[0]["id"] == "1"
