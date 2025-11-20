# ingenious/services/azure_search/tests/azure_search/test_preserve_unmatched_semantic.py
"""Test preservation of unmatched documents during semantic reranking.

Focus on pipeline-level `_apply_semantic_ranking`: if the semantic reranker
returns no rows, the original fused documents (top-50) should be preserved,
and their `_final_score` should fall back to `_fused_score`.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from ingenious.services.azure_search.components.pipeline import AdvancedSearchPipeline

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


@pytest.mark.asyncio
async def test_apply_semantic_ranking_preserves_unmatched_top50(
    config: Any,
    async_iter: Callable[[list[dict[str, Any]]], AsyncIterator[dict[str, Any]]],
) -> None:
    """Pipeline returns preserved docs when reranker yields no rows."""
    rerank_client: MagicMock = MagicMock()
    rerank_client.search = AsyncMock(return_value=async_iter([]))

    pipeline: AdvancedSearchPipeline = AdvancedSearchPipeline(
        config=config,
        retriever=MagicMock(),
        fuser=MagicMock(),
        answer_generator=MagicMock(),
        rerank_client=rerank_client,
    )

    fused: list[dict[str, Any]] = [
        {"id": "A,1", "content": "alpha", "_fused_score": 0.72},
        {"id": "B", "content": "beta", "_fused_score": 0.55},
    ]

    out: list[dict[str, Any]] = await pipeline._apply_semantic_ranking("any query", fused)
    ids: set[Any] = {d.get("id") for d in out}
    assert {"A,1", "B"} <= ids

    preserved: dict[str, Any] = next(d for d in out if d["id"] == "A,1")
    assert preserved.get("_fused_score") == 0.72
    assert preserved.get("content") == "alpha"


@pytest.mark.asyncio
async def test_pipeline_semantic_rerank_preserves_unmatched(
    monkeypatch: MonkeyPatch,
    async_iter: Callable[[list[dict[str, Any]]], AsyncIterator[dict[str, Any]]],
) -> None:
    """Filter construction + preservation when reranker returns none."""
    cfg = SimpleNamespace(id_field="id", semantic_configuration_name="default")

    monkeypatch.setattr(
        "ingenious.services.azure_search.components.pipeline.QueryType",
        SimpleNamespace(SEMANTIC="semantic"),
        raising=False,
    )

    rerank_client = MagicMock()
    rerank_client.search = AsyncMock(return_value=async_iter([]))
    pipeline = AdvancedSearchPipeline(
        config=cfg,
        retriever=MagicMock(),
        fuser=MagicMock(),
        answer_generator=MagicMock(),
        rerank_client=rerank_client,
    )

    fused: list[dict[str, Any]] = [
        {"id": "A,1", "_fused_score": 0.72, "content": "alpha"},
        {"id": "B", "_fused_score": 0.55, "content": "beta"},
    ]

    out: list[dict[str, Any]] = await pipeline._apply_semantic_ranking("any query", fused)
    ids: set[Any] = {d.get("id") for d in out}
    assert "A,1" in ids

    doc: dict[str, Any] = next(d for d in out if d["id"] == "A,1")
    assert doc.get("_final_score") == 0.72
    assert doc.get("content") == "alpha"
