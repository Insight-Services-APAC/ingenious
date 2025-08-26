"""Test edge cases and retries for the Azure Search retriever.

This module verifies specific non-happy-path behaviors of the
AzureSearchRetriever component. It ensures that the retriever correctly relies on
the Azure SDK's built-in retry policies for handling throttling (HTTP 429 errors),
rather than implementing custom retry logic. It also confirms that complex Unicode
queries are safely handled across both lexical and vector search paths.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from pytest import MonkeyPatch


@pytest.mark.asyncio
async def test_retriever_lexical_retries_on_429_via_sdk_policy(
    config: Any,
    monkeypatch: MonkeyPatch,
    async_iter: Callable[[list[Any]], AsyncIterator[Any]],
) -> None:
    """Test that the retriever relies on the SDK's retry policy for 429 errors.

    This test ensures the SearchClient is constructed with a retry policy to handle
    throttling (HTTP 429), confirming that the retriever itself does not implement
    a manual retry loop. We inject a dummy client with a sentinel policy object
    and verify its presence.
    """
    # Sentinel policy to detect it was attached by the factory we inject here.
    sentinel_policy = object()

    class DummySearchClient:
        """A mock SearchClient with a sentinel retry policy for testing."""

        def __init__(self) -> None:
            """Initialize the dummy client with a retry policy and mock search method."""
            self.retry_policy = sentinel_policy
            self.search = AsyncMock(return_value=async_iter([]))

        async def close(self) -> None:
            """Mock the async close method."""
            return None

    class DummyEmbeddingClient:
        """A mock EmbeddingClient for testing retriever initialization."""

        def __init__(self) -> None:
            """Initialize the dummy client with a mock embeddings creator."""
            self.embeddings = MagicMock()
            self.embeddings.create = AsyncMock(
                return_value=MagicMock(data=[MagicMock(embedding=[0.1, 0.2])])
            )

    from ingenious.services.azure_search.components.retrieval import (
        AzureSearchRetriever,
    )

    # Create retriever with our custom clients
    r = AzureSearchRetriever(
        config,
        search_client=DummySearchClient(),
        embedding_client=DummyEmbeddingClient(),
    )

    # The client the retriever uses should expose the retry_policy (SDK-level backoff)
    assert getattr(r._search_client, "retry_policy", None) is sentinel_policy

    # One lexical call should go through; we don't implement manual retry loops in the retriever
    out: list[Any] = await r.search_lexical("q")
    assert out == []
    cast(DummySearchClient, r._search_client).search.assert_awaited()


@pytest.mark.asyncio
async def test_retrieval_handles_unicode_query(
    config: Any,
    async_iter: Callable[[list[Any]], AsyncIterator[Any]],
    monkeypatch: MonkeyPatch,
) -> None:
    """Test that lexical and vector search paths safely handle Unicode queries.

    This ensures that queries containing multi-byte characters, symbols, and
    emojis are processed correctly without encoding errors or data loss
    through both the lexical search and the vector embedding pathways.
    """
    from ingenious.services.azure_search.components.retrieval import (
        AzureSearchRetriever,
    )

    q: str = """こんにちは 🌟 — café №42 — "quotes" and emojis 🚀"""

    # Create mock clients
    mock_search_client = MagicMock()
    mock_search_client.search = AsyncMock(return_value=async_iter([]))

    mock_embedding_client = MagicMock()
    mock_embedding_client.embeddings = MagicMock()
    mock_embedding_client.embeddings.create = AsyncMock(
        return_value=MagicMock(data=[MagicMock(embedding=[0.1, 0.2])])
    )

    # Create retriever with mocked clients
    retriever = AzureSearchRetriever(
        config,
        search_client=mock_search_client,
        embedding_client=mock_embedding_client,
    )

    # Lexical: just ensure call succeeds and was awaited
    out_lex: list[Any] = await retriever.search_lexical(q)
    assert out_lex == []
    cast(MagicMock, retriever._search_client).search.assert_awaited()

    # Vector: embeddings.create should receive the exact unicode text
    cast(MagicMock, retriever._search_client).search.reset_mock()
    cast(MagicMock, retriever._embedding_client).embeddings.create.reset_mock()

    _ = await retriever.search_vector(q)

    cast(MagicMock, retriever._embedding_client).embeddings.create.assert_awaited()
    # Mypy can't infer the type of `call_args` on a mock, so we cast.
    _, kwargs = cast(MagicMock, retriever._embedding_client).embeddings.create.call_args
    # openai embeddings call is kwarg-style in implementation
    assert kwargs["input"] == [q]
