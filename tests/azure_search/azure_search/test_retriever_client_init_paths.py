# ingenious/services/azure_search/tests/azure_search/test_provider_client_init_paths.py
"""Ensure pipeline client factories are used for retrieval.

This module provides integration tests for the AzureSearchProvider's retrieval
path. It verifies that the provider correctly uses the client_init factories to
obtain its Azure Search and OpenAI clients. To avoid network dependencies,
these tests use dummy (stub) clients that mimic the real async clients'
interfaces, allowing for isolated and fast execution.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, AsyncIterator, Tuple
from unittest.mock import patch

import pytest

from ingenious.config.main_settings import IngeniousSettings
from ingenious.config.models import AzureSearchSettings, ModelSettings
from ingenious.services.azure_search.provider import AzureSearchProvider


class _AsyncIter:
    """Async iterator over a list of documents for SearchClient.search."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        """Initialize the async iterator with a list of documents.

        Args:
            rows: A list of dicts, where each dict represents a document.
        """
        self._rows: list[dict[str, Any]] = rows

    def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        """Return the iterator object itself."""
        return self

    async def __anext__(self) -> dict[str, Any]:
        """Return the next document in the list asynchronously.

        Raises:
            StopAsyncIteration: When all documents have been yielded.
        """
        if not self._rows:
            raise StopAsyncIteration
        return self._rows.pop(0)


class _DummyAsyncSearchClient:
    """Closeable async SearchClient stub with a permissive `search`."""

    def __init__(self) -> None:
        """Initialize the dummy search client."""
        self.calls: list[Tuple[str, int]] = []

    async def search(self, *args: Any, **kwargs: Any) -> _AsyncIter:
        """Simulate a search query, returning a fixed list of documents.

        Ignores all arguments and returns a predefined async iterator of results.

        Args:
            *args: Positional arguments (ignored).
            **kwargs: Keyword arguments (ignored).

        Returns:
            An async iterator yielding dummy search documents.
        """
        docs: list[dict[str, Any]] = [
            {"id": "D1", "content": "doc-1", "@search.score": 0.3},
            {"id": "D2", "content": "doc-2", "@search.score": 0.2},
        ]
        return _AsyncIter(docs)

    async def close(self) -> None:
        """Simulate closing the client connection."""
        return None


class _DummyEmbeddings:
    """Stub for the OpenAI embeddings client."""

    async def create(self, *args: Any, **kwargs: Any) -> Any:
        """Simulate creating an embedding vector.

        Args:
            *args: Positional arguments (ignored).
            **kwargs: Keyword arguments (ignored).

        Returns:
            A namespace object mimicking the OpenAI embeddings response structure.
        """
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])])


class _DummyChatCompletions:
    """Stub for the OpenAI chat completions client."""

    async def create(self, *args: Any, **kwargs: Any) -> Any:
        """Simulate a chat completion response.

        Args:
            *args: Positional arguments (ignored).
            **kwargs: Keyword arguments (ignored).

        Returns:
            A namespace object mimicking the OpenAI chat completion response.
        """
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="3 3"))])


class _DummyChat:
    """Stub for the OpenAI chat object."""

    def __init__(self) -> None:
        """Initialize the dummy chat object."""
        self.completions = _DummyChatCompletions()


class _DummyAsyncOpenAI:
    """Closeable AsyncOpenAI stub serving embeddings + chat completions."""

    def __init__(self) -> None:
        """Initialize the dummy OpenAI client."""
        self.embeddings = _DummyEmbeddings()
        self.chat = _DummyChat()

    async def close(self) -> None:
        """Simulate closing the client connection."""
        return None


def _settings() -> IngeniousSettings:
    """Create a mock IngeniousSettings object for testing.

    This provides the necessary configuration for the AzureSearchProvider without
    needing to load settings from the environment or a file.

    Returns:
        A configured IngeniousSettings instance for tests.
    """
    s = IngeniousSettings.model_construct()
    s.models = [
        ModelSettings(
            model="text-embedding-3-small",
            deployment="emb",
            api_key="ok",
            base_url="https://aoai.example.com",
            api_version="2024-02-01",
        ),
        ModelSettings(
            model="gpt-5",
            deployment="chat",
            api_key="ok",
            base_url="https://aoai.example.com",
            api_version="2024-02-01",
        ),
    ]
    s.azure_search_services = [
        AzureSearchSettings(
            service="svc",
            endpoint="https://s.example.net",
            key="sk",
            index_name="idx",
            semantic_ranking=False,
        )
    ]
    return s


@pytest.mark.asyncio
async def test_provider_retrieve_uses_client_factories() -> None:
    """Verify provider uses client_init factories and retrieval works."""
    made_sc: int = 0
    made_aoai: int = 0

    def _mk_sc(*_a: Any, **_k: Any) -> _DummyAsyncSearchClient:
        """Factory for creating a dummy search client and tracking calls."""
        nonlocal made_sc
        made_sc += 1
        return _DummyAsyncSearchClient()

    def _mk_aoai(*_a: Any, **_k: Any) -> _DummyAsyncOpenAI:
        """Factory for creating a dummy OpenAI client and tracking calls."""
        nonlocal made_aoai
        made_aoai += 1
        return _DummyAsyncOpenAI()

    # Patch client_init factories (used by the provider's pipeline builder)
    with (
        patch(
            "ingenious.services.azure_search.client_init.make_async_search_client",
            new=_mk_sc,
        ),
        patch(
            "ingenious.services.azure_search.client_init.make_async_openai_client",
            new=_mk_aoai,
        ),
    ):
        provider = AzureSearchProvider(_settings(), enable_answer_generation=False)

        out: list[dict[str, Any]] = await provider.retrieve("what is fusion?", top_k=2)
        assert isinstance(out, list) and out, "Expected non-empty retrieval output."
        assert made_sc >= 1, "Expected make_async_search_client to be used."
        assert made_aoai >= 1, "Expected make_async_openai_client to be used."

        await provider.close()
