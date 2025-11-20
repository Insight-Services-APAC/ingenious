"""Test edge cases for the Azure Search vector retriever component.

This module contains tests for the `AzureSearchRetriever` specifically focusing
on its vector search capabilities (`search_vector` method). The goal is to
validate behavior with unusual inputs like empty queries or unicode characters,
ensuring the component is robust and interacts correctly with its dependencies
(like the embedding client and the search client) under these conditions.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable
from unittest.mock import AsyncMock

import pytest

from ingenious.services.azure_search.components.retrieval import AzureSearchRetriever

if TYPE_CHECKING:
    from ingenious.services.azure_search.config import SearchConfig


@pytest.mark.asyncio
async def test_retriever_empty_query_short_circuits_embedding(
    config: SearchConfig, async_iter: Callable[[list[Any]], AsyncIterator[Any]]
) -> None:
    """Ensure vector search with an empty query returns an empty list without side effects.

    This test verifies that calling `search_vector` with an empty string ("")
    correctly short-circuits. It should not invoke the embedding client or the
    Azure Search service, preventing unnecessary API calls and potential errors.
    """
    # Embedding client: must NOT be called for empty query
    embedding_client: Any = SimpleNamespace(
        embeddings=SimpleNamespace(create=AsyncMock()),
        close=AsyncMock(),
    )

    # Search client: should also NOT be called if short-circuiting is in place
    search_client: Any = SimpleNamespace(
        search=AsyncMock(return_value=async_iter([])),
        close=AsyncMock(),
    )

    retriever = AzureSearchRetriever(
        config=config,
        search_client=search_client,
        embedding_client=embedding_client,
    )

    out: list[dict[str, Any]] = await retriever.search_vector("")  # empty query

    # Expect graceful empty result and no downstream calls
    assert out == [], "Vector path should return [] for empty query"
    embedding_client.embeddings.create.assert_not_called()
    search_client.search.assert_not_called()

    # Clean-up
    await retriever.close()
    search_client.close.assert_awaited()
    embedding_client.close.assert_awaited()


@pytest.mark.asyncio
async def test_retriever_unicode_query_vector_path(
    config: SearchConfig,
    async_iter: Callable[[list[dict[str, Any]]], AsyncIterator[dict[str, Any]]],
) -> None:
    """Ensure vector search correctly handles unicode queries and documents.

    This test exercises the full vector search path with a unicode query string.
    It confirms that the query is passed to the embedding client correctly and that
    the resulting search query to Azure Search is properly formed. It also checks
    that unicode content from search results is processed without errors.
    """
    query: str = "naïve café ☕️ – 東京"

    # Embeddings.create returns a fixed vector
    embedding_vector: list[float] = [0.01, 0.02, 0.03]
    embeddings_create = AsyncMock(
        return_value=SimpleNamespace(data=[SimpleNamespace(embedding=embedding_vector)])
    )
    embedding_client: Any = SimpleNamespace(
        embeddings=SimpleNamespace(create=embeddings_create),
        close=AsyncMock(),
    )

    # Search client yields unicode docs
    docs: list[dict[str, Any]] = [
        {"id": "γ", "@search.score": 0.93, config.content_field: "smörgåsbord"},
        {"id": "δ", "@search.score": 0.81, config.content_field: "renée"},
    ]
    search_mock = AsyncMock(return_value=async_iter(docs))
    search_client: Any = SimpleNamespace(search=search_mock, close=AsyncMock())

    retriever = AzureSearchRetriever(
        config=config,
        search_client=search_client,
        embedding_client=embedding_client,
    )

    out: list[dict[str, Any]] = await retriever.search_vector(query)

    # Output order and tagging
    assert [d["id"] for d in out] == ["γ", "δ"]
    assert out[0]["_retrieval_type"] == "vector_dense"
    assert out[0]["_retrieval_score"] == 0.93

    # Embeddings were invoked once with expected params
    embeddings_create.assert_awaited_once()
    e_kwargs: dict[str, Any] = embeddings_create.call_args.kwargs
    assert e_kwargs.get("input") == [query]
    assert e_kwargs.get("model") == config.embedding_deployment_name

    # Search invoked with a single DummyVectorizedQuery (patched in conftest.py)
    search_mock.assert_awaited_once()
    s_kwargs: dict[str, Any] = search_mock.call_args.kwargs
    assert s_kwargs.get("search_text") is None
    assert s_kwargs.get("top") == config.top_k_retrieval

    vqs: Any = s_kwargs.get("vector_queries")
    assert isinstance(vqs, list) and len(vqs) == 1
    vq: Any = vqs[0]
    # Conftest patches VectorizedQuery → DummyVectorizedQuery; introspect attrs
    assert getattr(vq, "vector", None) == embedding_vector
    assert getattr(vq, "k_nearest_neighbors", None) == config.top_k_retrieval
    assert getattr(vq, "fields", None) == config.vector_field
    assert getattr(vq, "exhaustive", None) is True

    # Clean-up
    await retriever.close()
    search_client.close.assert_awaited()
    embedding_client.close.assert_awaited()
