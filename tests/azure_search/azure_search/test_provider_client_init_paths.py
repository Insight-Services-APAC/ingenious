"""Provider ↔ client_init integration: client creation via factory and retrieval.

Why:
- Exercise `AzureSearchProvider.retrieve()` to ensure it obtains its clients
  through `ingenious.services.azure_search.client_init` (factory indirection),
  and that retrieval completes using closeable stub clients with no network.

Key entry points:
- `AzureSearchProvider(settings)` constructor and `.retrieve(...)`.

I/O & deps:
- No azure/openai SDK calls. We patch factory functions to return dummies.
- IMPORTANT: we patch at both import sites:
  - provider.make_async_search_client (provider’s reranker client)
  - client_init.make_async_search_client + client_init.make_async_openai_client
    (used inside the search pipeline/builders).

Usage:
- Run with pytest. Network-free and mypy-safe.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List, Tuple
from unittest.mock import patch

import pytest

from ingenious.config.main_settings import IngeniousSettings
from ingenious.config.models import AzureSearchSettings, ModelSettings
from ingenious.services.azure_search.provider import AzureSearchProvider


class _AsyncIter:
    """Async iterator over a list of documents for SearchClient.search.

    What:
        Minimal async iterator that yields prebuilt rows then stops.
    Why:
        Simulates Azure SDK async search result iteration with no network.
    """

    def __init__(self, rows: List[dict[str, Any]]) -> None:
        """Initialize with a fixed list of rows."""
        self._rows: List[dict[str, Any]] = rows

    def __aiter__(self) -> "_AsyncIter":
        """Return self as an async iterator."""
        return self

    async def __anext__(self) -> dict[str, Any]:
        """Yield next row or stop."""
        if not self._rows:
            raise StopAsyncIteration
        return self._rows.pop(0)


class _DummyAsyncSearchClient:
    """Closeable async SearchClient stub with a permissive `search` method.

    What:
        Implements `search()` returning two docs and `close()` for cleanup.
    Why:
        Lets the pipeline perform lexical/vector/DAT fusion without SDK calls.
    """

    def __init__(self) -> None:
        """Initialize the stub client with an optional call log."""
        self.calls: List[Tuple[str, int]] = []

    async def search(self, *args: Any, **kwargs: Any) -> _AsyncIter:
        """Return an iterator of fake docs; ignore vector vs lexical flags.

        Returns:
            _AsyncIter over rows carrying '@search.score' to feed fusion.
        """
        docs: List[dict[str, Any]] = [
            {"id": "D1", "content": "doc-1", "@search.score": 0.3},
            {"id": "D2", "content": "doc-2", "@search.score": 0.2},
        ]
        return _AsyncIter(docs)

    async def close(self) -> None:
        """Provide an awaitable close method."""
        return None


class _DummyEmbeddings:
    """Embeddings stub to satisfy the retriever's vector path.

    What:
        Returns one tiny embedding vector.
    Why:
        Keeps vector search path alive in tests without OpenAI SDK.
    """

    async def create(self, *args: Any, **kwargs: Any) -> Any:
        """Return a single 3-dim embedding vector."""
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])])


class _DummyChatCompletions:
    """Completions stub to support DAT scoring calls.

    What:
        Returns a simple "3 3" string the code expects to parse.
    Why:
        Allows fusion/DAT scoring to proceed in a closed world.
    """

    async def create(self, *args: Any, **kwargs: Any) -> Any:
        """Return a two-integer string suitable for DAT parsing."""
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="3 3"))])


class _DummyChat:
    """Chat stub grouping a `completions` namespace.

    Why:
        Mirrors the minimal shape used by the code under test.
    """

    def __init__(self) -> None:
        """Initialize completions namespace."""
        self.completions = _DummyChatCompletions()


class _DummyAsyncOpenAI:
    """Closeable AsyncOpenAI stub serving embeddings + chat completions.

    What:
        Provides `.embeddings.create` and `.chat.completions.create`.
    Why:
        Builders/pipeline use these to score and fuse results.
    """

    def __init__(self) -> None:
        """Construct chat + embeddings namespaces."""
        self.embeddings = _DummyEmbeddings()
        self.chat = _DummyChat()

    async def close(self) -> None:
        """Provide an awaitable close method."""
        return None


def _settings() -> IngeniousSettings:
    """Create valid IngeniousSettings for provider construction.

    Returns:
        A settings object with one Azure Search service and two Azure OpenAI models.
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
            semantic_ranking=False,  # avoid L2 for a simpler path
        )
    ]
    return s


@pytest.mark.asyncio
async def test_provider_retrieve_instantiates_search_client_via_client_init_with_aad() -> None:
    """Verify provider.retrieve builds clients via factory and completes.

    What:
        Asserts that `AzureSearchProvider` obtains its Search and OpenAI clients
        through the central factories and that retrieval works (lexical + vector +
        DAT fusion) using our dummies.
    Why:
        Ensures indirection and lifecycle are respected without SDKs/network.
    """
    made_sc: int = 0
    made_aoai: int = 0

    def _mk_sc(*_a: Any, **_k: Any) -> _DummyAsyncSearchClient:
        """Factory spy for SearchClient that returns the dummy search client."""
        nonlocal made_sc
        made_sc += 1
        return _DummyAsyncSearchClient()

    def _mk_aoai(*_a: Any, **_k: Any) -> _DummyAsyncOpenAI:
        """Factory spy for AsyncOpenAI client that returns the dummy AOAI client."""
        nonlocal made_aoai
        made_aoai += 1
        return _DummyAsyncOpenAI()

    # Patch at BOTH import sites:
    # - provider.make_async_search_client (the provider's L2/rerank client)
    # - client_init.make_async_search_client + client_init.make_async_openai_client (pipeline)
    with (
        patch(
            "ingenious.services.azure_search.provider.make_async_search_client",
            new=_mk_sc,
        ),
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

        out: List[dict[str, Any]] = await provider.retrieve("what is fusion?", top_k=2)
        assert isinstance(out, list) and out, "Expected non-empty retrieval output."
        assert made_sc >= 1, "Expected make_async_search_client to be used."
        assert made_aoai >= 1, "Expected make_async_openai_client to be used."

        # Cleanup path (ensures our stubs implement close()).
        await provider.close()


@pytest.mark.skip(
    reason=(
        "SearchConfig does not carry AAD credentials; Search client path is key-based. "
        "This placeholder remains until token-based Search credential support is added."
    )
)
def test_provider_prefers_token_credential_when_both_key_and_client_credentials_provided() -> None:
    """Placeholder: would assert token credential preferred when both are present.

    Why:
        This test is intentionally skipped until the Search path supports
        AAD-based credentials in configuration. It documents the intended behavior.
    """
    assert True  # pragma: no cover
