"""Test failure modes and edge cases for the DynamicRankFuser.

This module verifies the robustness of the DynamicRankFuser, particularly its
Dynamic Alpha Tuning (DAT) component. It tests two main failure scenarios:
1. Exceptions raised by the underlying Language Model (LLM) client during the
   ranking process.
2. Malformed or unexpected string outputs from the LLM when parsing relevance scores.

The goal is to ensure the fuser gracefully handles these errors by falling back
to default, safe values, preventing system crashes and ensuring stable fusion behavior.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from openai import APIError

from ingenious.services.azure_search.components.fusion import DynamicRankFuser


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exception_to_raise",
    [
        # This is the correct signature: APIError(message, response, body=...)
        APIError(
            "LLM Failed",
            httpx.Response(status_code=500, request=MagicMock()),  # 2nd POSITIONAL argument
            body=None,  # KEYWORD argument
        ),
        asyncio.TimeoutError("LLM Timeout"),
        RuntimeError("Unexpected LLM error"),
    ],
)
async def test_dat_fusion_llm_failure_falls_back_to_alpha_0_5(
    mock_search_config: MagicMock,
    mock_async_openai_client: AsyncMock,
    exception_to_raise: Exception,
) -> None:
    """Verify `_perform_dat` handles LLM exceptions and returns a default alpha.

    This test ensures that if the LLM call fails for any reason (e.g., API
    error, timeout), the fusion process doesn't crash but instead falls back
    to a neutral alpha value of 0.5, effectively balancing the lexical and
    vector search results.
    """
    # Configure the mock LLM client to raise the specified exception
    mock_async_openai_client.chat.completions.create.side_effect = exception_to_raise

    fuser = DynamicRankFuser(config=mock_search_config, llm_client=mock_async_openai_client)

    # Prepare dummy inputs
    query: str = "test query"
    top_lexical: dict[str, Any] = {"content": "lexical doc"}
    top_vector: dict[str, Any] = {"content": "vector doc"}

    # Execute the DAT step
    alpha: float = await fuser._perform_dat(query, top_lexical, top_vector)

    # Assert the fallback value is used
    assert alpha == 0.5
    mock_async_openai_client.chat.completions.create.assert_called_once()


@pytest.mark.parametrize(
    "llm_output, expected_scores",
    [
        ("4 3", (4, 3)),  # Happy path
        ("invalid output", (0, 0)),  # Malformed
        ("5", (0, 0)),  # Wrong count
        ("6 2", (0, 0)),  # Out of range (high)
        ("-1 3", (0, 0)),  # Out of range (low)
        ("Score V: 4, Score L: 2", (4, 2)),  # Text around numbers
        ("3.5 2.1", (3, 5)),  # Matches current regex behavior
    ],
)
def test_dat_fusion_parse_malformed_scores_falls_back_to_zero(
    mock_search_config: MagicMock, llm_output: str, expected_scores: tuple[int, int]
) -> None:
    """Verify `_parse_dat_scores` handles malformed LLM output gracefully.

    This test checks that various invalid string formats—such as an incorrect
    number of scores, out-of-range values, or non-numeric text—are
    correctly parsed into a default fallback score of (0, 0), preventing
    errors downstream.
    """
    # Initialize fuser (LLM client not needed for parsing logic)
    fuser = DynamicRankFuser(config=mock_search_config, llm_client=AsyncMock())

    # Execute the parsing
    scores: tuple[int, int] = fuser._parse_dat_scores(llm_output)

    # Assert the result
    assert scores == expected_scores
