"""Retrieval tests: pass explicit dummy clients instead of None."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ingenious.services.azure_search.components.retrieval import AzureSearchRetriever
from ingenious.services.azure_search.config import SearchConfig


class _DummyLexClient:
    async def search(self, *args, **kwargs):
        class _Iter:
            def __init__(self):
                self._done = False

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._done:
                    raise StopAsyncIteration
                self._done = True
                return {"id": "l1", "content": "lex", "@search.score": 0.5}

        return _Iter()

    async def close(self):
        return None


class _DummyEmbeddings:
    async def create(self, *args, **kwargs):
        # Must return OpenAI-like shape: obj.data[0].embedding
        from types import SimpleNamespace

        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])])


@pytest.mark.asyncio
async def test_search_lexical(config: SearchConfig) -> None:
    """Use a provided dummy search client."""
    retr = AzureSearchRetriever(
        config, search_client=_DummyLexClient(), embedding_client=_DummyEmbeddings()
    )
    out = await retr.search_lexical("q")
    assert out and out[0]["id"] == "l1"


@pytest.mark.asyncio
async def test_search_vector(config: SearchConfig) -> None:
    """Test vector search successfully executes with embedding client.

    Verifies that search_vector method properly uses the embedding client
    to generate embeddings and executes vector search against Azure Search.
    """
    emb_client = SimpleNamespace(embeddings=_DummyEmbeddings())  # 👈 OpenAI shape
    retr = AzureSearchRetriever(
        config, search_client=_DummyLexClient(), embedding_client=emb_client
    )
    out = await retr.search_vector("q")
    assert out and out[0]["id"] in {"l1", "v1"}  # depending on your dummy search body


@pytest.mark.asyncio
async def test_retriever_close(config: SearchConfig) -> None:
    """Test retriever close method completes without errors.

    Verifies that calling close() on the retriever properly cleans up
    resources without raising exceptions.
    """
    emb_client = SimpleNamespace(embeddings=_DummyEmbeddings())
    retr = AzureSearchRetriever(
        config, search_client=_DummyLexClient(), embedding_client=emb_client
    )
    await retr.close()  # success = no exception
