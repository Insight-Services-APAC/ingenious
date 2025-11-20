"""Provider factory one-shot fallback: ensure _clean_sources is applied.

Why:
- The final link in the provider fallback chain should pass results through
  the pipeline's cleaning step (even when using a one-shot factory client).
- This test spies on _clean_sources to assert that internal fields are removed.

Usage:
- Patches client_init._get_factory to return a "patched" factory (module name
  ending in ".tests") so the provider takes the factory one-shot path.
"""

from __future__ import annotations

from typing import Any, List

import pytest
from pydantic import SecretStr


class _AsyncIter:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def __aiter__(self) -> "_AsyncIter":
        return self

    async def __anext__(self) -> dict[str, Any]:
        if not self._rows:
            raise StopAsyncIteration
        return self._rows.pop(0)


@pytest.mark.asyncio
async def test_provider_factory_oneshot_applies_cleaning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rows returned via factory one-shot must be cleaned via _clean_sources."""
    # Stub pipeline with a cleaning function that strips internal fields.
    from ingenious.services.azure_search import provider as mod

    cleaned_calls: list[List[dict[str, Any]]] = []

    class _StubPipeline:
        def __init__(self) -> None:
            self.retriever = type("R", (), {"_search_client": None})()

        async def retrieve(self, *_: Any, **__: Any) -> list[dict[str, Any]]:
            return []

        def _clean_sources(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            cleaned_calls.append(rows)
            out: list[dict[str, Any]] = []
            for r in rows:
                d = dict(r)
                d.pop("_retrieval_score", None)
                d.pop("@search.captions", None)
                out.append(d)
            return out

    monkeypatch.setattr(
        mod, "build_search_pipeline", lambda *_a, **_k: _StubPipeline(), raising=True
    )

    # Patch a "tests" factory so provider uses the one-shot path.
    from ingenious.services.azure_search import client_init as ci

    class _OneShotClient:
        async def search(self, *_, **__):
            return _AsyncIter(
                [
                    {
                        "id": "A",
                        "content": "x",
                        "_retrieval_score": 1.0,
                        "@search.captions": [{"text": "t"}],
                    }
                ]
            )

        async def close(self) -> None:
            return None

    class _Factory:
        __module__ = "ingenious.services.azure_search.tests.fake"

        @staticmethod
        def create_async_search_client(
            *, index_name: str, config: dict[str, Any], **__: Any
        ) -> _OneShotClient:  # noqa: D401
            return _OneShotClient()

    monkeypatch.setattr(ci, "_get_factory", lambda: _Factory, raising=True)

    from ingenious.services.azure_search.config import SearchConfig

    cfg = SearchConfig(
        search_endpoint="https://x",
        search_key=SecretStr("k"),
        search_index_name="idx",
        openai_endpoint="https://o",
        openai_key=SecretStr("ok"),
        embedding_deployment_name="emb",
        generation_deployment_name="gen",
    )

    p = mod.AzureSearchProvider(cfg)
    rows = await p.retrieve("q", top_k=3)
    await p.close()

    # Assert the cleaner was called and the returned rows are stripped.
    assert cleaned_calls, "Cleaner should have been invoked"
    assert rows and rows[0]["id"] == "A"
    assert "_retrieval_score" not in rows[0]
    assert "@search.captions" not in rows[0]
