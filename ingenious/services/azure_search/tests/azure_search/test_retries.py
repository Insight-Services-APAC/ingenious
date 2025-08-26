"""Verify AzureSearchRetriever works with clients that have internal retries.

This module contains unit tests for the AzureSearchRetriever. Its primary purpose
is to ensure that the retriever operates correctly when the underlying Azure SDK
clients (for search or embeddings) handle transient errors like HTTP 429
(Too Many Requests) using their own internal retry mechanisms.

These tests use mock clients (`FlakySearchClient`, `FlakyEmbeddingsClient`) to
simulate this behavior without making actual network calls. This validates that our
retriever does not need its own duplicative retry logic for such scenarios.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Iterator, cast

import pytest

# Keep this import path as in your project
from ingenious.services.azure_search.components.retrieval import AzureSearchRetriever


class _AsyncResults:
    """Mimic the async iterator returned by SearchClient.search()."""

    _docs: list[dict[str, Any]]
    _it: Iterator[dict[str, Any]] | None

    def __init__(self, docs: list[dict[str, Any]]) -> None:
        """Initialize the async iterator with a set of documents.

        Args:
            docs: A list of document-like dictionaries to be yielded.
        """
        self._docs = docs
        self._it = None

    def __aiter__(self) -> _AsyncResults:
        """Return the async iterator object itself."""
        self._it = iter(self._docs)
        return self

    async def __anext__(self) -> dict[str, Any]:
        """Yield the next document in the iterator."""
        try:
            # The iterator is guaranteed to be initialized by `__aiter__`.
            it = cast(Iterator[dict[str, Any]], self._it)
            return next(it)
        except StopIteration:
            raise StopAsyncIteration


class FlakySearchClient:
    """
    Simulates an Azure Search client with internal retry policy:
    two 429 "failures" then success — all inside a single .search() call.
    """

    calls: int
    attempts: int

    def __init__(self) -> None:
        """Initialize counters for calls and internal attempts."""
        self.calls = 0  # how many times retriever called .search()
        self.attempts = 0  # internal retry attempts within the client

    async def search(self, *args: Any, **kwargs: Any) -> _AsyncResults:
        """Simulate a search call that retries twice internally before succeeding."""
        self.calls += 1
        # Simulate the SDK's internal retry loop: 2 failures then success
        for _ in range(3):
            self.attempts += 1
            if self.attempts <= 2:
                # pretend we saw a 429 and the client will retry internally
                # (no need to raise; the SDK would catch and retry)
                await asyncio.sleep(0)
                continue
            # success on third attempt
            return _AsyncResults([{"id": "1", "content": "ok", "@search.score": 2.0}])


class DummyEmbeddingsClient:
    """Minimal embeddings client (not used by lexical test, but required by ctor)."""

    embeddings: DummyEmbeddingsClient

    def __init__(self) -> None:
        """Initialize the client, exposing self via the `embeddings` attribute."""
        self.embeddings = self

    async def create(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
        """Return a mock successful embedding result."""
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.0])])


@pytest.mark.asyncio
async def test_retry_on_429_then_success() -> None:
    """
    Validates we succeed through the normal call path when the underlying
    client handles transient 429s via its own retry policy.
    """
    cfg = SimpleNamespace(
        top_k_retrieval=1,
        embedding_deployment_name="unused-here",
    )

    client = FlakySearchClient()
    # The retriever expects specific client types. We ignore the type mismatch
    # to inject our mock client for this unit test.
    r = AzureSearchRetriever(
        config=cfg,
        search_client=client,
        embedding_client=DummyEmbeddingsClient(),
    )

    # NOTE: search_lexical only takes (query), top_k is read from config
    docs: list[dict[str, Any]] = await r.search_lexical("hello")

    # Retriever should call the client's .search() exactly once,
    # while the client itself performed 3 internal attempts.
    assert client.calls == 1, "Retriever should invoke SearchClient.search once"
    assert client.attempts == 3, "Expected 2 internal retries (3 total attempts)"
    assert isinstance(docs, list) and docs and docs[0]["content"] == "ok"


class _FlakyEmbeddings:
    async def create(self, *args, **kwargs):
        exc = RuntimeError("429 Too Many Requests")
        setattr(exc, "status_code", 429)
        raise exc


class _NoopSearch:
    async def search(self, *args, **kwargs):
        raise AssertionError("search() should not be reached")


@pytest.mark.asyncio
async def test_vector_embed_429_fallback_or_retry(config):
    # 👇 Make the client look like OpenAI: client.embeddings.create(...)
    emb_client = SimpleNamespace(embeddings=_FlakyEmbeddings())
    retr = AzureSearchRetriever(
        config, search_client=_NoopSearch(), embedding_client=emb_client
    )
    with pytest.raises(RuntimeError):
        await retr.search_vector("q")
