"""Provider unit tests — focus on delegation and preflight checks."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from ingenious.config.main_settings import IngeniousSettings
from ingenious.config.models import AzureSearchSettings, ModelSettings
from ingenious.services.azure_search.provider import AzureSearchProvider
from ingenious.services.retrieval.errors import GenerationDisabledError


def _make_settings() -> IngeniousSettings:
    s = IngeniousSettings.model_construct()
    s.models = [
        ModelSettings(
            model="text-embedding-3-small",
            deployment="embed",
            api_key="K",
            base_url="https://oai.example.com",
            api_version="2024-02-01",
        ),
        ModelSettings(
            model="gpt-5",
            deployment="chat",
            api_key="K",
            base_url="https://oai.example.com",
            api_version="2024-02-01",
        ),
    ]
    s.azure_search_services = [
        AzureSearchSettings(
            service="svc",
            endpoint="https://search.example.net",
            key="SK",
            index_name="idx",
        )
    ]
    return s


@pytest.mark.asyncio
async def test_provider_retrieve_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that provider retrieve method delegates to pipeline.

    Verifies that AzureSearchProvider.retrieve properly delegates search
    queries to the underlying pipeline's retrieve method.
    """
    settings = _make_settings()
    pipeline = MagicMock()
    pipeline.retrieve = AsyncMock(return_value=[{"id": "A", "content": "Alpha"}])

    monkeypatch.setattr(
        "ingenious.services.azure_search.provider.build_search_pipeline",
        lambda _cfg: pipeline,
        raising=False,
    )
    p = AzureSearchProvider(settings)
    docs = await p.retrieve("q", top_k=1)
    assert docs and docs[0]["id"] == "A"
    await p.close()


@pytest.mark.parametrize("async_close", [True, False])
@pytest.mark.asyncio
async def test_provider_close_tolerates_sync_or_async(
    monkeypatch: pytest.MonkeyPatch, async_close: bool
) -> None:
    """Test that provider close handles both sync and async pipeline close methods.

    Verifies that the provider's close method can handle pipelines with either
    synchronous or asynchronous close implementations.
    """
    settings = _make_settings()
    pipeline = MagicMock()
    if async_close:
        pipeline.close = AsyncMock()
    else:
        pipeline.close = MagicMock(return_value=None)

    monkeypatch.setattr(
        "ingenious.services.azure_search.provider.build_search_pipeline",
        lambda _cfg: pipeline,
        raising=False,
    )

    p = AzureSearchProvider(settings)
    await p.close()
    if async_close:
        pipeline.close.assert_awaited()
    else:
        pipeline.close.assert_called_once()


@pytest.mark.asyncio
async def test_provider_answer_blank_query_short_circuits(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that provider answer method short-circuits on blank queries.

    Verifies that blank or whitespace-only queries return a helpful message
    without calling the pipeline's get_answer method.
    """
    settings = _make_settings()
    pipeline = MagicMock()
    pipeline.get_answer = AsyncMock()

    monkeypatch.setattr(
        "ingenious.services.azure_search.provider.build_search_pipeline",
        lambda _cfg: pipeline,
        raising=False,
    )

    p = AzureSearchProvider(settings, enable_answer_generation=True)

    with caplog.at_level(logging.INFO, logger=AzureSearchProvider.__module__):
        out = await p.answer("  \t   ")

    assert out == {
        "answer": "Please enter a question so I can search the knowledge base.",
        "source_chunks": [],
    }
    pipeline.get_answer.assert_not_awaited()
    assert any("Blank query provided" in rec.getMessage() for rec in caplog.records)
    await p.close()


@pytest.mark.asyncio
async def test_provider_answer_raises_when_generation_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that provider answer raises error when generation is disabled.

    Verifies that calling answer() when enable_answer_generation is False
    raises a GenerationDisabledError.
    """
    settings = _make_settings()
    pipeline = MagicMock()
    pipeline.get_answer = AsyncMock()

    monkeypatch.setattr(
        "ingenious.services.azure_search.provider.build_search_pipeline",
        lambda _cfg: pipeline,
        raising=False,
    )

    p = AzureSearchProvider(settings, enable_answer_generation=False)
    with pytest.raises(GenerationDisabledError):
        await p.answer("non-blank")
    pipeline.get_answer.assert_not_awaited()
    await p.close()


@pytest.mark.asyncio
async def test_provider_answer_passes_query_unmodified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that provider passes queries to pipeline without modification.

    Verifies that queries including whitespace are passed to the pipeline's
    get_answer method exactly as received without trimming or normalization.
    """
    settings = _make_settings()

    captured: dict[str, str] = {}

    async def fake_get_answer(q: str) -> dict[str, Any]:
        captured["q"] = q
        return {"answer": "A", "source_chunks": []}

    pipeline = MagicMock()
    pipeline.get_answer = AsyncMock(side_effect=fake_get_answer)

    monkeypatch.setattr(
        "ingenious.services.azure_search.provider.build_search_pipeline",
        lambda _cfg: pipeline,
        raising=False,
    )

    p = AzureSearchProvider(settings, enable_answer_generation=True)
    messy = "  some  query   with   spaces  "
    await p.answer(messy)
    assert captured["q"] == messy
    await p.close()
