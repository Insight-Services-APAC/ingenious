"""Tests for the DynamicRankFuser component.

This module contains unit and integration tests for the `DynamicRankFuser` class,
which is responsible for performing Dynamic Alpha Fusion (DAT) on search results.
The tests verify the correctness of individual helper methods (alpha calculation,
score parsing, normalization) and the end-to-end fusion logic. It ensures that
LLM interactions for DAT are correctly handled, including success and failure
paths, and that the final fused list is correctly scored and ordered.

Dependencies are mocked to isolate the fuser's logic, particularly the
`AsyncOpenAI` client used for generating DAT scores.
"""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pytest import MonkeyPatch

from ingenious.services.azure_search.components.fusion import DynamicRankFuser
from ingenious.services.azure_search.config import SearchConfig


@pytest.fixture
def fuser(config: SearchConfig) -> DynamicRankFuser:
    """Provides a DynamicRankFuser instance for testing."""
    return DynamicRankFuser(config)


@pytest.mark.parametrize(
    "sv,sl,exp",
    [
        (0, 0, 0.5),
        (5, 2, 1.0),
        (1, 5, 0.0),
        (3, 3, 0.5),
        (4, 1, 0.8),
        (1, 4, 0.2),
        (5, 5, 0.5),
        (1, 2, 0.3),
        (2, 1, 0.7),
    ],
)
def test_calculate_alpha_cases(fuser: DynamicRankFuser, sv: int, sl: int, exp: float) -> None:
    """Tests the alpha calculation logic across various score inputs.

    This ensures the formula correctly translates DAT scores into a fusion
    weight `alpha` between 0.0 and 1.0, handling edge cases and rounding.
    """
    assert fuser._calculate_alpha(sv, sl) == exp


@pytest.mark.parametrize(
    "out,expected",
    [
        ("3 4", (3, 4)),
        (" 5 1 ", (5, 1)),
        ("Dense=5; BM=2 (ok)", (5, 2)),
        ("0 0", (0, 0)),
        ("3 4 5", (3, 4)),
    ],
)
def test_parse_scores_ok(fuser: DynamicRankFuser, out: str, expected: tuple[int, int]) -> None:
    """Tests successful parsing of valid DAT score strings from the LLM.

    This verifies that the regex can robustly extract the two integer scores
    from various expected output formats.
    """
    assert fuser._parse_dat_scores(out) == expected


@pytest.mark.parametrize("out", ["", "3", "A B"])
def test_parse_scores_bad(fuser: DynamicRankFuser, out: str) -> None:
    """Tests the DAT score parser's fallback for malformed strings.

    Ensures that if the LLM returns a non-numeric or incomplete string,
    the parser gracefully fails and returns neutral (0, 0) scores.
    """
    assert fuser._parse_dat_scores(out) == (0, 0)


@pytest.mark.parametrize("out", ["6 4", "3 9", "-1 3"])
def test_parse_scores_oob(fuser: DynamicRankFuser, out: str) -> None:
    """Tests the DAT score parser's fallback for out-of-bounds numbers.

    Verifies that scores outside the expected 0-5 range are rejected,
    triggering the (0, 0) fallback to prevent invalid alpha values.
    """
    assert fuser._parse_dat_scores(out) == (0, 0)


def test_normalize_scores_paths(fuser: DynamicRankFuser) -> None:
    """Tests the min-max score normalization logic for various scenarios.

    This covers standard cases, lists with identical scores, lists with only
    zeros, empty lists, and lists containing invalid or missing score values.
    It ensures a `_normalized_score` between 0.0 and 1.0 is always added.
    """
    rows: list[dict[str, Any]] = [
        {"id": "A", "_retrieval_score": 20.0},
        {"id": "B", "_retrieval_score": 15.0},
        {"id": "C", "_retrieval_score": 10.0},
    ]
    fuser._normalize_scores(rows)
    assert rows[0]["_normalized_score"] == 1.0
    assert rows[1]["_normalized_score"] == 0.5
    assert rows[2]["_normalized_score"] == 0.0

    same: list[dict[str, Any]] = [
        {"id": "A", "_retrieval_score": 5.0},
        {"id": "B", "_retrieval_score": 5.0},
    ]
    fuser._normalize_scores(same)
    assert same[0]["_normalized_score"] == 0.5 == same[1]["_normalized_score"]

    zeros: list[dict[str, Any]] = [{"id": "A", "_retrieval_score": 0.0}]
    fuser._normalize_scores(zeros)
    # Spec-compliant degeneracy: neutral 0.5 even when all scores are zero
    assert zeros[0]["_normalized_score"] == 0.5

    empty: list[dict[str, Any]] = []
    fuser._normalize_scores(empty)
    assert empty == []

    invalid: list[dict[str, Any]] = [
        {"id": "A", "_retrieval_score": 10.0},
        {"id": "B", "_retrieval_score": None},
        {"id": "C", "_retrieval_score": "bad"},
        {"id": "D"},
        {"id": "E", "_retrieval_score": 5.0},
    ]
    fuser._normalize_scores(invalid)
    assert invalid[0]["_normalized_score"] == 1.0
    assert invalid[1]["_normalized_score"] == 0.0
    assert invalid[2]["_normalized_score"] == 0.0
    assert invalid[3]["_normalized_score"] == 0.0
    assert invalid[4]["_normalized_score"] == 0.5


@pytest.mark.asyncio
async def test_perform_dat_success(
    fuser: DynamicRankFuser, config: SearchConfig, monkeypatch: MonkeyPatch
) -> None:
    """Tests a successful LLM call to perform Dynamic Alpha Tuning.

    Verifies that the correct prompt is constructed, the LLM client is called,
    and the response is parsed to produce the final alpha value.
    """
    # Replace client method to return desired "5 3"
    mock_create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="5 3"))]
        )
    )
    monkeypatch.setattr(fuser._llm_client.chat.completions, "create", mock_create)

    long_content = "X" * 2000
    alpha = await fuser._perform_dat(
        "Q", {config.content_field: "A"}, {config.content_field: long_content}
    )
    assert alpha == 1.0
    mock_create.assert_awaited()


@pytest.mark.asyncio
async def test_perform_dat_error_fallback(
    fuser: DynamicRankFuser, monkeypatch: MonkeyPatch
) -> None:
    """Tests the fallback mechanism when the DAT LLM call fails.

    Ensures that if the client raises an exception (e.g., API error),
    the process doesn't fail and instead returns a neutral alpha of 0.5.
    """
    monkeypatch.setattr(
        fuser._llm_client.chat.completions,
        "create",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    alpha = await fuser._perform_dat("Q", {"content": "a"}, {"content": "b"})
    assert alpha == 0.5


@pytest.mark.asyncio
async def test_fuse_e2e_and_fast_paths(fuser: DynamicRankFuser, monkeypatch: MonkeyPatch) -> None:
    """Tests the end-to-end fusion logic and edge cases.

    This test verifies the complete fusion process, including DAT, normalization,
    and Reciprocal Rank Fusion (RRF). It also checks the fast-path logic for when
    one of the input lists is empty and ensures documents without IDs are ignored.
    """
    # Alpha = 0.6
    monkeypatch.setattr(fuser, "_perform_dat", AsyncMock(return_value=0.6))
    lexical: list[dict[str, Any]] = [
        {"id": "A", "content": "A", "_retrieval_score": 10.0, "_retrieval_type": "lex"},
        {"id": "B", "content": "B", "_retrieval_score": 8.0, "_retrieval_type": "lex"},
        {"id": "C", "content": "C", "_retrieval_score": 5.0, "_retrieval_type": "lex"},
    ]
    vector: list[dict[str, Any]] = [
        {"id": "C", "content": "C", "_retrieval_score": 0.9, "_retrieval_type": "vec"},
        {"id": "D", "content": "D", "_retrieval_score": 0.8, "_retrieval_type": "vec"},
        {"id": "E", "content": "E", "_retrieval_score": 0.7, "_retrieval_type": "vec"},
    ]
    fused = await fuser.fuse("Q", lexical, vector)
    assert [r["id"] for r in fused] == ["C", "A", "D", "B", "E"]
    assert math.isclose(fused[0]["_fused_score"], 0.6)
    assert fused[0]["_retrieval_type"].startswith("hybrid_dat_alpha")

    # one-list-empty paths
    vec_only = await fuser.fuse("Q", [], [{"id": "V1", "_retrieval_score": 0.9}])
    assert 0.0 <= vec_only[0]["_fused_score"] <= 1.0
    # and check order:
    assert [r["id"] for r in vec_only] == ["V1"]  # or the expected top-N sequence
    lex_only = await fuser.fuse("Q", [{"id": "L1", "_retrieval_score": 1.1}], [])
    # Single-list case uses per-method min–max; degenerate positive → 0.5, α=0.0 → fused 0.5
    assert lex_only[0]["_fused_score"] == 0.5

    # missing id ignored
    out = await fuser.fuse(
        "Q",
        [{"id": "L1", "_retrieval_score": 1.0}, {"_retrieval_score": 0.1}],
        [{"id": "V1", "_retrieval_score": 0.2}],
    )
    assert {d.get("id") for d in out} == {"L1", "V1"}


@pytest.mark.asyncio
async def test_fuser_close(fuser: DynamicRankFuser, monkeypatch: MonkeyPatch) -> None:
    """Tests that closing the fuser also closes the underlying LLM client.

    This ensures proper resource management by verifying that the `close` method
    on the fuser is correctly propagated to its internal `AsyncOpenAI` client.
    """
    mock_close = AsyncMock()
    monkeypatch.setattr(fuser._llm_client, "close", mock_close)
    await fuser.close()
    mock_close.assert_awaited_once()
