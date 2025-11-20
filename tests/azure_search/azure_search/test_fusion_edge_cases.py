"""Tests edge cases for the DynamicRankFuser component.

This module focuses on verifying the behavior of the DynamicRankFuser,
specifically its internal methods like score normalization, under unusual
or degenerate conditions. These tests ensure numerical stability and
prevent unexpected outcomes like division by zero when input data deviates
from the common case (e.g., all scores being identical).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from ingenious.services.azure_search.components.fusion import DynamicRankFuser


def test_fusion_normalize_scores_degenerate_case_equals_0_5(
    mock_search_config: Any,
) -> None:
    """Verify _normalize_scores sets all scores to 0.5 when max_score equals min_score.

    This test handles the degenerate case where all retrieval scores are identical.
    In this scenario, the standard min-max normalization formula would result in
    division by zero. The expected behavior is to assign a neutral midpoint
    score of 0.5 to all results, ensuring stable and predictable output.
    """
    fuser = DynamicRankFuser(config=mock_search_config, llm_client=AsyncMock())

    # Case 1: All scores are the same (non-zero)
    results_same: list[dict[str, Any]] = [
        {"id": "1", "_retrieval_score": 10.0},
        {"id": "2", "_retrieval_score": 10.0},
        {"id": "3", "_retrieval_score": 10.0},
    ]
    fuser._normalize_scores(results_same)
    assert all(r["_normalized_score"] == 0.5 for r in results_same)

    # Case 2: All scores are zero
    results_zero: list[dict[str, Any]] = [
        {"id": "1", "_retrieval_score": 0.0},
        {"id": "2", "_retrieval_score": 0.0},
    ]
    fuser._normalize_scores(results_zero)
    assert all(r["_normalized_score"] == 0.5 for r in results_zero)

    # Case 3: Single result
    results_single: list[dict[str, Any]] = [
        {"id": "1", "_retrieval_score": 5.0},
    ]
    fuser._normalize_scores(results_single)
    assert results_single[0]["_normalized_score"] == 0.5
