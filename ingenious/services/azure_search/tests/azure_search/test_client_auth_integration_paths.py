"""Integration path: provider -> pipeline -> client_init factory.

This test verifies that client instances are created via the public factory seam
at `ingenious.services.azure_search.client_init.AzureClientFactory`. We patch that
symbol directly (not internals of components.pipeline) and assert a successful
retrieve call consumes the patched factory products.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

logging.getLogger("ingenious.services.azure_search.provider").setLevel(logging.DEBUG)


class _AsyncIter:
    """Minimal async iterator over a single document row."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        """Initialize with rows to yield once."""
        self._rows = rows
        self._i = 0

    def __aiter__(self) -> "_AsyncIter":
        """Return self as async iterator."""
        return self

    async def __anext__(self) -> dict[str, Any]:
        """Yield next row or stop."""
        if self._i >= len(self._rows):
            raise StopAsyncIteration
        row = self._rows[self._i]
        self._i += 1
        return row


class _DummyAsyncSearchClient:
    """Dummy async Azure Search client yielded by factory."""

    async def search(self, *args: Any, **kwargs: Any) -> _AsyncIter:
        """Return a short async iterator with one document result."""
        return _AsyncIter([{"id": "1", "content": "x", "@search.score": 1.0}])

    async def close(self) -> None:
        """No-op close (satisfies pipeline shutdown)."""
        return None


class _DummyEmbeddings:
    """Embeddings stub for OpenAI client."""

    async def create(self, *args: Any, **kwargs: Any) -> Any:
        """Return a structure matching OpenAI embeddings shape."""
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])])


class _DummyChatCompletions:
    """Chat completions stub for OpenAI client."""

    async def create(self, *args: Any, **kwargs: Any) -> Any:
        """Return a structure matching AOAI chat completions shape."""
        msg = SimpleNamespace(content="ok")
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class _DummyAsyncOpenAI:
    """Async OpenAI client carrying embeddings and chat stubs."""

    def __init__(self) -> None:
        """Wire sub-clients as attributes (AOAI compatibility)."""
        self.embeddings = _DummyEmbeddings()
        self.chat = SimpleNamespace(completions=_DummyChatCompletions())

    async def close(self) -> None:
        """No-op close."""
        return None


class _Factory:
    """Patched AzureClientFactory exposing async creators used by client_init."""

    @staticmethod
    def create_async_search_client(
        *, index_name: str, config: dict[str, Any], **_: Any
    ) -> _DummyAsyncSearchClient:
        """Return dummy search client; assert config fields are mapped."""
        assert config["endpoint"]
        assert config["search_key"]
        assert index_name
        return _DummyAsyncSearchClient()

    @staticmethod
    def create_async_openai_client(
        *, config: dict[str, Any], api_version: str, **_: Any
    ) -> _DummyAsyncOpenAI:
        """Return dummy AOAI client; assert config forwarding."""
        assert config["openai_endpoint"]
        assert config["openai_key"]
        assert api_version
        return _DummyAsyncOpenAI()


@pytest.mark.asyncio
async def test_provider_retrieve_instantiates_clients_via_pipeline_factories() -> None:
    settings = SimpleNamespace(
        models=[
            SimpleNamespace(
                role="embedding", deployment="emb", endpoint="https://aoai", api_key="k"
            ),
            SimpleNamespace(
                role="chat", deployment="gen", endpoint="https://aoai", api_key="k"
            ),
        ],
        azure_search_services=[
            SimpleNamespace(
                endpoint="https://search",
                key="sk",
                index_name="idx",
                use_semantic_ranking=False,
            )
        ],
    )

    # 👇 Patch the correct seam
    with patch(
        "ingenious.services.azure_search.client_init.AzureClientFactory", _Factory
    ):
        from ingenious.services.azure_search.provider import AzureSearchProvider

        provider = AzureSearchProvider(
            settings_or_config=settings, enable_answer_generation=False
        )
        try:
            rows = await provider.retrieve("q", top_k=1)
            assert rows and rows[0]["id"] == "1"
        finally:
            await provider.close()
