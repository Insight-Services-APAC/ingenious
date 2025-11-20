"""Tests failure modes and fallback behaviors for the AdvancedSearchPipeline.

This module contains integration tests that verify the resilience of the search
pipeline when its components, such as the Azure Search client for semantic
reranking, encounter exceptions. The primary goal is to ensure that failures
are handled gracefully, providing a reasonable fallback result to the user
instead of a complete error.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from azure.core.exceptions import HttpResponseError

from ingenious.services.azure_search.components.pipeline import AdvancedSearchPipeline

if TYPE_CHECKING:
    from unittest.mock import MagicMock


@pytest.mark.asyncio
async def test_pipeline_l2_semantic_ranking_failure_falls_back_to_dat_scores(
    mock_search_config: MagicMock,
) -> None:
    """Tests that a semantic ranking failure falls back to using fused scores.

    This test simulates an `HttpResponseError` from the Azure Search client during
    the L2 semantic reranking step. It verifies that the pipeline catches this
    exception and correctly uses the pre-existing `_fused_score` as the
    `_final_score` for each document, returning the original list of results
    without modification.

    Args:
        mock_search_config: A mock search configuration object fixture.
    """
    # Mock components
    mock_retriever: AsyncMock = AsyncMock()
    mock_fuser: AsyncMock = AsyncMock()
    mock_generator: AsyncMock = AsyncMock()
    mock_rerank_client: AsyncMock = AsyncMock()

    # Configure the rerank client to fail
    mock_rerank_client.search.side_effect = HttpResponseError(
        "Azure Search Service Unavailable (503)"
    )

    pipeline: AdvancedSearchPipeline = AdvancedSearchPipeline(
        config=mock_search_config,
        retriever=mock_retriever,
        fuser=mock_fuser,
        answer_generator=mock_generator,
        rerank_client=mock_rerank_client,
    )

    # Prepare input data (fused results)
    fused_results: list[dict[str, object]] = [
        {"id": "1", "content": "Doc 1", "_fused_score": 0.9},
        {"id": "2", "content": "Doc 2", "_fused_score": 0.8},
    ]
    query: str = "test query"

    # Execute the L2 ranking step
    ranked_results: list[dict[str, object]] = await pipeline._apply_semantic_ranking(
        query, fused_results
    )

    # Assert the search client was called
    mock_rerank_client.search.assert_called()

    # Assert the fallback behavior: the results list is the same object (or identical content)
    assert ranked_results == fused_results

    # Assert that _final_score was correctly populated from _fused_score during the fallback
    assert ranked_results[0]["_final_score"] == 0.9
    assert ranked_results[1]["_final_score"] == 0.8
