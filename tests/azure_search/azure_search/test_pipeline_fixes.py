"""Tests edge cases for the Azure Search semantic reranking filter logic.

This module contains tests for the AdvancedSearchPipeline's semantic reranking
functionality. Specifically, it verifies that document IDs containing special
characters (like commas or single quotes) are correctly escaped and formatted
into a valid OData filter string. This ensures the secondary search call for
reranking does not fail due to malformed filter syntax.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from ingenious.services.azure_search.components.pipeline import AdvancedSearchPipeline
from ingenious.services.azure_search.config import SearchConfig


@pytest.mark.asyncio
async def test_pipeline_semantic_rerank_id_escaping_or_clause(
    config: SearchConfig, async_iter: Callable[[list[Any]], AsyncIterator[Any]]
) -> None:
    """Verify OData 'OR' filter is safely constructed for semantic reranking.

    This test ensures that when document IDs contain special characters like
    commas or single quotes, the _apply_semantic_ranking method correctly
    escapes them and builds a valid OData filter using 'eq' and 'or' clauses.
    This prevents syntax errors when the pipeline calls the search service for
    L2 reranking, a safer alternative to the 'search.in()' function.
    """
    # Setup: Initialize pipeline with mocked dependencies
    r, f, g = MagicMock(), MagicMock(), MagicMock()
    rerank_client = MagicMock()
    # Configure the rerank client mock; we only care about the arguments it receives.
    # Return an empty iterator as we are focused on the input arguments.
    rerank_client.search = AsyncMock(return_value=async_iter([]))

    # Ensure the config uses a standard 'id' field
    config = config.model_copy(update={"id_field": "id"})

    pipeline = AdvancedSearchPipeline(config, r, f, g, rerank_client=rerank_client)

    # Input: Fused results with IDs containing commas and single quotes
    fused_results: list[dict[str, Any]] = [
        {"id": "A,1", "content": "Doc with comma", "_fused_score": 0.9},
        {"id": "B'2", "content": "Doc with quote", "_fused_score": 0.8},
        {"id": "C", "content": "Normal doc", "_fused_score": 0.7},
    ]

    # Execute
    await pipeline._apply_semantic_ranking("test query", fused_results)

    # Assert: Check the arguments passed to the rerank client's search method
    rerank_client.search.assert_awaited_once()
    assert rerank_client.search.call_args is not None  # Ensures call_args is not None for mypy
    call_kwargs: dict[str, Any] = rerank_client.search.call_args.kwargs
    filter_query: str | None = call_kwargs.get("filter")

    # The expected filter uses 'eq' and 'or', and escapes the single quote in B'2
    # We check for the presence of each clause rather than the exact string match due to potential ordering differences.
    expected_clauses: list[str] = [
        "id eq 'A,1'",
        "id eq 'B''2'",  # OData escapes single quotes by doubling them
        "id eq 'C'",
    ]

    assert filter_query is not None
    for clause in expected_clauses:
        assert clause in filter_query, (
            f"Missing or incorrect clause in filter: {clause}\nGenerated filter: {filter_query}"
        )

    # Ensure it doesn't use the vulnerable search.in() syntax
    assert "search.in(" not in filter_query, (
        f"Filter query should use 'OR' clause, not 'search.in()'.\nGenerated filter: {filter_query}"
    )
