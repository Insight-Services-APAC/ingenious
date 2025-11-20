"""Validate OData OR filter construction in pipeline._apply_semantic_ranking."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, AsyncIterator, Callable, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from ingenious.services.azure_search.components.pipeline import AdvancedSearchPipeline
from ingenious.services.azure_search.config import SearchConfig


@pytest.mark.asyncio
async def test_pipeline_semantic_filter_escaping_or_clause(
    config: SearchConfig,
    async_iter: Callable[[list[dict[str, Any]]], AsyncIterator[dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test semantic ranking constructs proper OData OR filter with escaping.

    Verifies that document IDs containing special characters (commas, quotes)
    are properly escaped in the OData filter clause for semantic reranking.
    """
    # Build pipeline with dummy components
    p = AdvancedSearchPipeline(config, MagicMock(), MagicMock(), MagicMock())

    # Ensure QueryType symbol exists on module (some codepaths/patches rely on it)
    monkeypatch.setattr(
        "ingenious.services.azure_search.components.pipeline.QueryType",
        SimpleNamespace(SEMANTIC="semantic"),
        raising=False,
    )

    # Rerank client: we only inspect kwargs to 'search'
    p._rerank_client = MagicMock()
    p._rerank_client.search = AsyncMock(return_value=async_iter([]))

    fused = [
        {"id": "A,1", "content": "alpha", "_fused_score": 0.9},
        {"id": "B'2", "content": "bravo", "_fused_score": 0.8},
        {"id": "C", "content": "charlie", "_fused_score": 0.7},
    ]

    await p._apply_semantic_ranking("q", fused)

    p._rerank_client.search.assert_awaited_once()
    filter_query = cast(str, p._rerank_client.search.call_args.kwargs.get("filter"))
    assert filter_query is not None

    expected_clauses = ["id eq 'A,1'", "id eq 'B''2'", "id eq 'C'"]
    for clause in expected_clauses:
        assert clause in filter_query
    assert "search.in(" not in filter_query
    assert " or " in filter_query.lower()
