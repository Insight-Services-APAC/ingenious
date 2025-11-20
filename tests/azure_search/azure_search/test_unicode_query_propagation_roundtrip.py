"""Tests Unicode query handling in the AzureSearchRetriever.

This module verifies that the AzureSearchRetriever correctly processes and
transmits Unicode characters through its entire retrieval pipeline, including
both lexical and vector search paths. It ensures that complex strings with
multi-byte characters, symbols, and special punctuation are passed verbatim
to the Azure Search and embedding services without malformation.

The primary entry point is the `test_unicode_query_roundtrip_lexical_and_vector`
test case.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, AsyncIterator, Callable
from unittest.mock import AsyncMock

import pytest

from ingenious.services.azure_search.components.retrieval import AzureSearchRetriever


@pytest.mark.asyncio
async def test_unicode_query_roundtrip_lexical_and_vector(
    config: Any, async_iter: Callable[[list[Any]], AsyncIterator[Any]]
) -> None:
    """Verify lexical and vector search paths preserve Unicode characters.

    This test provides unique coverage by ensuring that:
      - The *lexical* call passes the exact Unicode query in `search_text`,
        including curly quotes and the numero sign.
      - The embedding creation process sees the same unmodified Unicode text.
      - The *vector* call sends `vector_queries`, confirming the correct path is used
        without duplicating more detailed assertions from other tests.
    """
    UNI: str = "こんにちは 🌟 — café №42 — “quotes” 🚀"

    # --- Search client stub that inspects per-call kwargs --------------------
    call_counter: dict[str, int] = {"n": 0}

    async def _search_side_effect(*_a: Any, **kwargs: Any) -> AsyncIterator[Any]:
        """Mock the search client's search method to inspect call arguments.

        It distinguishes between the first (lexical) and second (vector) calls
        to assert that the correct keyword arguments were passed for each path.
        """
        call_counter["n"] += 1
        if call_counter["n"] == 1:
            # Lexical path: assert the exact Unicode string and top passed through
            assert kwargs.get("search_text") == UNI
            assert kwargs.get("top") == config.top_k_retrieval
        else:
            # Vector path: don't duplicate deep assertions; just ensure vector_queries are present
            assert "vector_queries" in kwargs
        return async_iter([])

    search_client = SimpleNamespace(
        search=AsyncMock(side_effect=_search_side_effect),
        close=AsyncMock(),
    )

    # --- Embeddings client stub that accepts either string or [string] -------
    async def _embed_create(**kwargs: Any) -> SimpleNamespace:
        """Mock the embedding client's create method to inspect its input.

        This ensures the raw Unicode string is passed to the embedding
        service without modification, whether as a direct string or as the
        sole element in a list.
        """
        got: str | list[str] | None = kwargs.get("input")
        if isinstance(got, list):
            assert len(got) == 1 and got[0] == UNI
        else:
            assert got == UNI
        # Minimal OpenAI-like shape
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.0, 0.0, 0.0])])

    embedding_client = SimpleNamespace(
        embeddings=SimpleNamespace(create=AsyncMock(side_effect=_embed_create)),
        close=AsyncMock(),
    )

    # --- Run the retriever under test ----------------------------------------
    retriever = AzureSearchRetriever(
        config, search_client=search_client, embedding_client=embedding_client
    )

    # Lexical: empty iterator → []
    out_lex: list[Any] = await retriever.search_lexical(UNI)
    assert out_lex == []

    # Vector: empty iterator → []
    out_vec: list[Any] = await retriever.search_vector(UNI)
    assert out_vec == []

    # Sanity: both paths executed; embeddings used once
    assert search_client.search.await_count == 2
    assert embedding_client.embeddings.create.await_count == 1

    # Cleanup
    await retriever.close()
    search_client.close.assert_awaited()
    embedding_client.close.assert_awaited()
