"""Tests for provider fallback and pipeline failure modes.

This module verifies the behavior of the AzureSearchProvider's fallback
mechanisms when the primary retrieval pipeline yields no results. It tests
two fallback paths: one using a raw client from the retriever and another
using a one-shot client from a factory.

Additionally, it confirms that the AdvancedSearchPipeline correctly handles
and re-raises exceptions from its fusion component as a fatal DAT error.

Key entry points are the `test_*` async functions.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr


class _AsyncIter:
    """A minimal async iterator over a list of dictionary-based rows."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        """Initializes the async iterator with data.

        Args:
            rows: A list of dictionaries to iterate over.
        """
        self._rows = rows

    def __aiter__(self) -> _AsyncIter:
        """Returns the iterator object itself."""
        return self

    async def __anext__(self) -> dict[str, Any]:
        """Returns the next item from the list.

        Raises:
            StopAsyncIteration: When all items have been yielded.

        Returns:
            The next row from the list.
        """
        if not self._rows:
            raise StopAsyncIteration
        return self._rows.pop(0)


@pytest.mark.asyncio
async def test_provider_fallback_raw_client_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider should use retriever's search client if the pipeline is empty."""
    # This test ensures that if the main `retrieve` method of the search pipeline
    # returns no results, the provider correctly falls back to using the raw
    # `_search_client` attached to the pipeline's retriever component.

    class _Client:
        """A stub for the raw Azure Search client."""

        async def search(self, *_: Any, **__: Any) -> _AsyncIter:
            """Mocks the search method to return a predefined result."""
            return _AsyncIter([{"id": "1", "@search.score": 1.0, "content": "c"}])

        async def close(self) -> None:
            """Mocks the async close method."""
            ...

    class _StubPipeline:
        """A stub pipeline that returns no results to trigger fallback."""

        def __init__(self) -> None:
            """Initializes the stub pipeline and its retriever."""
            self.retriever = SimpleNamespace(_search_client=self._make_client())

        async def retrieve(self, *_: Any, **__: Any) -> list[dict[str, Any]]:
            """Mocks the main retrieve method to return an empty list."""
            return []

        def _make_client(self) -> _Client:
            """Creates a mock client instance for the retriever."""
            return _Client()

        def _clean_sources(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            """A pass-through mock of the source cleaning method."""
            return rows

    from ingenious.services.azure_search import provider as mod

    monkeypatch.setattr(mod, "build_search_pipeline", lambda *_a, **_k: _StubPipeline())

    from ingenious.services.azure_search.config import SearchConfig

    cfg = SearchConfig(
        search_endpoint="https://x",
        search_key=SecretStr("k"),
        search_index_name="idx",
        openai_endpoint="https://o",
        openai_key=SecretStr("ok"),
        embedding_deployment_name="emb",
        generation_deployment_name="gen",
    )
    provider = mod.AzureSearchProvider(cfg)
    rows = await provider.retrieve("q", top_k=1)

    assert rows and rows[0]["id"] == "1"
    await provider.close()


@pytest.mark.asyncio
async def test_provider_fallback_factory_one_shot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provider should use a factory one-shot client as a second fallback."""
    # This test verifies the second level of fallback. If the pipeline returns
    # empty and the retriever's `_search_client` is also absent, the provider
    # should attempt to create a new, one-shot search client via a factory.

    from ingenious.services.azure_search import client_init as ci
    from ingenious.services.azure_search import provider as mod

    class _StubPipeline:
        """A stub pipeline that forces fallback by returning no results."""

        def __init__(self) -> None:
            """Initializes the retriever with a null `_search_client`."""
            self.retriever = SimpleNamespace(_search_client=None)

        async def retrieve(self, *_: Any, **__: Any) -> list[dict[str, Any]]:
            """Mocks the retrieve method to return an empty list."""
            return []

        def _clean_sources(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            """A pass-through mock of the source cleaning method."""
            return rows

    class _OneShotClient:
        """A stub for the one-shot client created by the factory."""

        async def search(self, *_: Any, **__: Any) -> _AsyncIter:
            """Mocks the search method to return a predefined result."""
            return _AsyncIter([{"id": "Z", "@search.score": 2.0, "content": "cz"}])

        async def close(self) -> None:
            """Mocks the async close method."""
            ...

    class _Factory:
        """A stub factory for creating the one-shot client."""

        __module__ = "ingenious.services.azure_search.tests.fake"

        @staticmethod
        def create_async_search_client(
            *, index_name: str, config: dict[str, Any], **__: Any
        ) -> _OneShotClient:
            """Creates a mock client, asserting required params were passed."""
            assert index_name and config.get("endpoint") and config.get("search_key")
            return _OneShotClient()

    monkeypatch.setattr(mod, "build_search_pipeline", lambda *_a, **_k: _StubPipeline())
    monkeypatch.setattr(ci, "_get_factory", lambda: _Factory)

    from ingenious.services.azure_search.config import SearchConfig

    cfg = SearchConfig(
        search_endpoint="https://x",
        search_key=SecretStr("k"),
        search_index_name="idx",
        openai_endpoint="https://o",
        openai_key=SecretStr("ok"),
        embedding_deployment_name="emb",
        generation_deployment_name="gen",
    )
    provider = mod.AzureSearchProvider(cfg)
    rows = await provider.retrieve("q", top_k=3)

    assert rows and rows[0]["id"] == "Z"
    await provider.close()


@pytest.mark.asyncio
async def test_pipeline_dat_fusion_fatal_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch,  # noqa: ARG001 - Required by pytest
) -> None:
    """A fuser exception should be re-raised as a DAT Fusion RuntimeError."""
    # This test ensures that if the `fuse` method within the pipeline's fuser
    # component raises an exception, the pipeline catches it and re-raises it
    # as a specific RuntimeError, indicating a fatal data-at-rest (DAT) error.

    from ingenious.services.azure_search.components import pipeline as pl

    class _StubRetriever:
        """A stub retriever that provides results for fusion."""

        async def search_lexical(self, *_: Any, **__: Any) -> list[dict[str, Any]]:
            """Returns mock lexical search results."""
            return [{"id": "1", "@search.score": 1.0}]

        async def search_vector(self, *_: Any, **__: Any) -> list[dict[str, Any]]:
            """Returns mock vector search results."""
            return [{"id": "2", "@search.score": 1.0}]

        async def close(self) -> None:
            """Mocks the async close method."""
            ...

    class _BoomFuser:
        """A stub fuser designed to fail."""

        async def fuse(self, *_: Any, **__: Any) -> list[dict[str, Any]]:
            """Mocks the fuse method to always raise an exception."""
            raise RuntimeError("boom")

        async def close(self) -> None:
            """Mocks the async close method."""
            ...

    cfg = pl.SearchConfig(
        search_endpoint="https://x",
        search_key=SecretStr("k"),
        search_index_name="idx",
        openai_endpoint="https://o",
        openai_key=SecretStr("ok"),
        embedding_deployment_name="emb",
        generation_deployment_name="gen",
    )
    pipe = pl.AdvancedSearchPipeline(config=cfg, retriever=_StubRetriever(), fuser=_BoomFuser())
    with pytest.raises(RuntimeError, match="DAT Fusion failed"):
        await pipe.retrieve("q", top_k=5)
    await pipe.close()
