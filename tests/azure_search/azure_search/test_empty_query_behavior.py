# ingenious/services/azure_search/tests/azure_search/test_empty_query_behavior.py
"""Tests graceful handling of empty queries in the Azure Search service.

This module verifies that the core components, specifically the AzureSearchRetriever
and the AdvancedSearchPipeline, behave correctly and efficiently when given an
empty or whitespace-only query string. The primary goal is to prevent unnecessary
and potentially costly downstream API calls, such as to OpenAI for embeddings or
to a large language model for answer generation. Instead, the system should return
a graceful, empty result or a helpful message.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, NoReturn

import pytest

from ingenious.services.azure_search.components.pipeline import AdvancedSearchPipeline
from ingenious.services.azure_search.components.retrieval import AzureSearchRetriever
from ingenious.services.azure_search.config import SearchConfig


class _AsyncEmptyResults:
    """Async iterator that yields nothing, mimicking an empty Azure Search page."""

    def __aiter__(self) -> AsyncIterator[Any]:
        return self

    async def __anext__(self) -> NoReturn:
        raise StopAsyncIteration


class _CloseableAioSearchClient:
    """Async SearchClient stub that returns empty results and supports async close()."""

    async def search(self, *args: Any, **kwargs: Any) -> _AsyncEmptyResults:
        return _AsyncEmptyResults()

    async def close(self) -> None:
        return None


class _NoEmbedOpenAI:
    """Embeddings stub that *fails* if called and supports async close()."""

    class _Embeddings:
        async def create(self, *args: Any, **kwargs: Any) -> NoReturn:
            raise AssertionError("embeddings.create should not be called for empty query")

    def __init__(self) -> None:
        self.embeddings: _NoEmbedOpenAI._Embeddings = self._Embeddings()

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_retriever_empty_query_returns_empty_or_graceful(
    config: SearchConfig,
) -> None:
    """Retriever returns [] for empty query; embeddings/search not invoked."""
    retriever = AzureSearchRetriever(
        config,
        search_client=_CloseableAioSearchClient(),
        embedding_client=_NoEmbedOpenAI(),
    )

    out_lex: list[Any] = await retriever.search_lexical(query="")
    assert out_lex == []

    out_vec: list[Any] = await retriever.search_vector(query="")
    assert out_vec == []

    await retriever.close()


@pytest.mark.asyncio
async def test_pipeline_empty_query_returns_friendly_message(
    config: SearchConfig,
) -> None:
    """Pipeline get_answer short-circuits to a friendly message on empty input."""

    class _StubRetriever:
        async def search_lexical(self, _q: str) -> list[Any]:
            return []

        async def search_vector(self, _q: str) -> list[Any]:
            return []

        async def close(self) -> None:
            pass

    class _StubFuser:
        async def fuse(self, _q: str, _lex: list[Any], _vec: list[Any]) -> list[Any]:
            return []

        async def close(self) -> None:
            pass

    class _StubAnswerGen:
        async def generate(self, *args: Any, **kwargs: Any) -> NoReturn:
            raise AssertionError("LLM/generation should not be called for empty query")

        async def close(self) -> None:
            pass

    config = config.copy(update={"enable_answer_generation": True})
    pipeline = AdvancedSearchPipeline(
        config=config,
        retriever=_StubRetriever(),  # type: ignore[arg-type]
        fuser=_StubFuser(),  # type: ignore[arg-type]
        answer_generator=_StubAnswerGen(),  # type: ignore[arg-type]
        rerank_client=_CloseableAioSearchClient(),  # required arg
    )

    result: Any = await pipeline.get_answer(query="")

    answer: str = ""
    sources: list[Any] = []
    if isinstance(result, tuple):
        answer, sources = result
    elif isinstance(result, dict):
        answer = result.get("answer", "")
        sources = result.get("source_chunks", result.get("sources", []))
    else:
        answer = getattr(result, "answer", "")
        sources = getattr(result, "sources", [])

    assert isinstance(answer, str) and answer.strip()
    assert sources == []
