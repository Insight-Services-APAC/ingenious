"""Tests Azure Search integration for queries with special characters.

This module verifies that the Azure Search retriever and pipeline components
correctly handle non-ASCII characters (Unicode) and special symbols (like commas)
in user queries and document IDs. It aims to prevent regressions related to
encoding, filter parsing, or client-side processing of such data.

The tests use mock Azure Search and Embedding clients to isolate the behavior
of the retriever and pipeline logic without making live network calls.
"""

# -*- coding: utf-8 -*-
from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, AsyncGenerator, Coroutine, Iterable
from unittest.mock import AsyncMock, MagicMock

import pytest

from ingenious.services.azure_search.components.pipeline import AdvancedSearchPipeline
from ingenious.services.azure_search.components.retrieval import AzureSearchRetriever

if TYPE_CHECKING:
    from collections.abc import Callable

    from ingenious.services.azure_search.config import SearchConfig


class _CloseableAioSearchClient:
    """A test stub for an async SearchClient with a mockable search() and close()."""

    def __init__(self) -> None:
        """Initializes the client with a default search mock that returns nothing."""
        # This default ensures that if a test forgets to override `search`, it
        # doesn't fail unexpectedly but instead returns an empty async iterator.
        self.search: AsyncMock = AsyncMock(
            side_effect=lambda *a, **k: _AsyncEmptyResults()
        )

    async def close(self) -> None:
        """Simulates closing the async client connection."""
        return None


class _AsyncEmptyResults:
    """An async iterator that yields no results."""

    def __aiter__(self) -> _AsyncEmptyResults:
        """Returns the iterator instance itself."""
        return self

    async def __anext__(self) -> None:
        """Stops the iteration immediately."""
        raise StopAsyncIteration


class _EmbeddingClientWithVector:
    """A test stub for an embedding client that returns a fixed vector."""

    class _Embeddings:
        """Inner class to mimic the client.embeddings.create() API structure."""

        def __init__(self, vector: list[float]) -> None:
            """
            Initializes the embedding generator.

            Args:
                vector: The fixed vector to return from the `create` method.
            """
            self._vector = list(vector)

        async def create(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
            """
            Generates a mock embedding response containing the pre-defined vector.

            This method mimics the OpenAI embedding client's response structure.
            """
            return SimpleNamespace(data=[SimpleNamespace(embedding=self._vector)])

    def __init__(self, vector: list[float]) -> None:
        """
        Initializes the client with a fixed vector for embeddings.

        Args:
            vector: The vector to be returned by the mock embedding service.
        """
        self.embeddings: _EmbeddingClientWithVector._Embeddings = self._Embeddings(
            vector
        )

    async def close(self) -> None:
        """Simulates closing the async client connection."""
        return None


@pytest.mark.asyncio
async def test_retriever_unicode_query_ok(
    config: SearchConfig,
    async_iter: Callable[
        [Iterable[dict[str, Any]]], AsyncGenerator[dict[str, Any], None]
    ],
) -> None:
    """Ensures Unicode/special chars in a query do not break search paths."""
    search_client = _CloseableAioSearchClient()
    embedding_client = _EmbeddingClientWithVector([0.01, 0.02, 0.03])

    retriever = AzureSearchRetriever(
        config,
        search_client=search_client,
        embedding_client=embedding_client,
    )

    # Lexical path: mock the search client to return two documents
    search_client.search = AsyncMock(
        return_value=async_iter(
            [
                {
                    "id": "α",
                    "@search.score": 2.1,
                    config.content_field: "naïve café ☕️ – 東京",
                },
                {"id": "β", "@search.score": 1.4, config.content_field: "crème brûlée"},
            ]
        )
    )
    out_lex: list[dict[str, Any]] = await retriever.search_lexical(
        "naïve café ☕️ – 東京"
    )
    assert [d["id"] for d in out_lex] == ["α", "β"]

    # Vector path: mock the search client again for the vector search results.
    # The embedding vector comes from our stub's `embeddings.create()` method.
    search_client.search = AsyncMock(
        return_value=async_iter(
            [
                {"id": "γ", "@search.score": 0.93, config.content_field: "smörgåsbord"},
                {"id": "δ", "@search.score": 0.81, config.content_field: "renée"},
            ]
        )
    )
    out_vec: list[dict[str, Any]] = await retriever.search_vector(
        "naïve café ☕️ – 東京"
    )
    assert [d["id"] for d in out_vec] == ["γ", "δ"]

    # Ensure the retriever's close() method correctly calls the clients' close methods.
    await retriever.close()


@pytest.mark.xfail(
    reason="IDs with commas break search.in(...) filter; current code may drop such docs. Consider escaping or fallback.",
    strict=False,
)
@pytest.mark.asyncio
async def test_apply_semantic_ranking_ids_with_commas_xfail(
    config: SearchConfig,
    async_iter: Callable[
        [Iterable[dict[str, Any]]], AsyncGenerator[dict[str, Any], None]
    ],
) -> None:
    """
    Tests that documents with commas in their IDs are handled gracefully.

    If a fused result ID contains a comma, the `search.in()` filter used for
    reranking can become ambiguous and fail. This test confirms the desired
    behavior: to gracefully keep the document (falling back to its fused score)
    even if the reranker returns no results for it.
    """
    # The actual clients are not used, so MagicMock is sufficient.
    pipeline = AdvancedSearchPipeline(config, MagicMock(), MagicMock(), MagicMock())

    # If the private helper being tested doesn't exist, skip this xfail test.
    if not hasattr(pipeline, "_apply_semantic_ranking"):
        pytest.skip(
            "AdvancedSearchPipeline._apply_semantic_ranking() not present; API changed."
        )

    # Simulate the reranker client returning nothing, as would happen with a
    # malformed filter string caused by the comma in the ID.
    pipeline._rerank_client = MagicMock()
    pipeline._rerank_client.search = AsyncMock(return_value=async_iter([]))

    fused: list[dict[str, Any]] = [
        {"id": "A,1", "_fused_score": 0.7, config.content_field: "C"}
    ]

    # The method may or may not be async, depending on implementation details.
    maybe: Coroutine[Any, Any, list[dict[str, Any]]] | list[dict[str, Any]] = (
        pipeline._apply_semantic_ranking("Q", fused)
    )
    out: list[dict[str, Any]] = await maybe if inspect.isawaitable(maybe) else maybe

    # Desired contract (currently xfail): the document is retained, falling
    # back to its original fused score.
    assert len(out) == 1 and out[0]["id"] == "A,1"
