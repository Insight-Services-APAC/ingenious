# -*- coding: utf-8 -*-
"""Pipeline tests: factory wiring, semantic rerank, cleaning, get_answer paths."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ingenious.services.azure_search.components.fusion import DynamicRankFuser
from ingenious.services.azure_search.components.generation import AnswerGenerator
from ingenious.services.azure_search.components.pipeline import (
    AdvancedSearchPipeline,
    build_search_pipeline,
)
from ingenious.services.azure_search.components.retrieval import AzureSearchRetriever
from ingenious.services.azure_search.config import SearchConfig


def test_build_search_pipeline_success(
    config: SearchConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that build_search_pipeline successfully constructs pipeline with all components.

    Verifies that the factory creates an AdvancedSearchPipeline with properly
    instantiated retriever, fuser, and generator components.
    """
    MockR = MagicMock()
    MockF = MagicMock()
    MockG = MagicMock()

    # Factories produce dummies; constructor receives injected clients (ignored here)
    monkeypatch.setattr(
        "ingenious.services.azure_search.components.pipeline.AzureSearchRetriever",
        MockR,
        raising=False,
    )
    monkeypatch.setattr(
        "ingenious.services.azure_search.components.pipeline.DynamicRankFuser",
        MockF,
        raising=False,
    )
    monkeypatch.setattr(
        "ingenious.services.azure_search.components.pipeline.AnswerGenerator",
        MockG,
        raising=False,
    )

    cfg = config.model_copy(update={"enable_answer_generation": True})
    p = build_search_pipeline(cfg)
    assert isinstance(p, AdvancedSearchPipeline)
    # We assert constructors were called (with kwargs — clients are injected by factory)
    assert MockR.call_count == 1
    assert MockF.call_count == 1
    assert MockG.call_count == 1


def test_build_search_pipeline_validation_error(
    config_no_semantic: SearchConfig,
) -> None:
    """Test that build_search_pipeline raises ValueError for invalid semantic config.

    Verifies that enabling semantic ranking without a semantic configuration
    name properly raises a validation error.
    """
    invalid = config_no_semantic.model_copy(
        update={"use_semantic_ranking": True, "semantic_configuration_name": None}
    )
    with pytest.raises(ValueError):
        build_search_pipeline(invalid)


def test_pipeline_init_sets_rerank_client(config: SearchConfig) -> None:
    """Test that pipeline initialization creates a rerank client.

    Verifies that AdvancedSearchPipeline constructor properly initializes
    the internal rerank client for semantic ranking operations.
    """
    r, f, g = (
        MagicMock(spec=AzureSearchRetriever),
        MagicMock(spec=DynamicRankFuser),
        MagicMock(spec=AnswerGenerator),
    )
    p = AdvancedSearchPipeline(config, r, f, g)
    assert hasattr(p, "_rerank_client")


@pytest.mark.asyncio
async def test_apply_semantic_ranking_happy(config: SearchConfig) -> None:
    """Test semantic ranking successfully reorders and enriches search results.

    Verifies that semantic reranking properly orders documents by reranker
    scores and merges metadata from the reranking API response.
    """
    r, f, g = MagicMock(), MagicMock(), MagicMock()
    p = AdvancedSearchPipeline(config, r, f, g)

    fused = [
        {"id": "A", "content": "A", "_fused_score": 0.8, "_retrieval_type": "hybrid"},
        {"id": "B", "content": "B", "_fused_score": 0.7, "_retrieval_type": "vector"},
    ]

    conftest_module: Any = __import__(
        "ingenious.services.azure_search.tests.conftest", fromlist=["AsyncIter"]
    )
    async_iter_mock = conftest_module.AsyncIter(
        [
            {"id": "B", "@search.reranker_score": 3.0, "content": "B2"},
            {"id": "A", "@search.reranker_score": 2.5, "content": "A2"},
        ]
    )

    with patch.object(p._rerank_client, "search", AsyncMock(return_value=async_iter_mock)):
        out = await p._apply_semantic_ranking("q", fused)

    assert [d["id"] for d in out] == ["B", "A"]
    assert out[0]["_final_score"] == 3.0
    assert out[0]["_fused_score"] == 0.7
    assert out[0]["content"] == "B2"


@pytest.mark.asyncio
async def test_apply_semantic_ranking_truncation(config: SearchConfig) -> None:
    """Test semantic ranking truncates to 50 documents for reranking API.

    Verifies that when fused results exceed 50 documents, only the top 50
    are sent for reranking while remaining documents are preserved.
    """
    r, f, g = MagicMock(), MagicMock(), MagicMock()
    p = AdvancedSearchPipeline(config, r, f, g)
    fused = [{"id": f"doc_{i}", "_fused_score": 1.0} for i in range(55)]

    conftest_module: Any = __import__(
        "ingenious.services.azure_search.tests.conftest", fromlist=["AsyncIter"]
    )
    async_iter_mock = conftest_module.AsyncIter(
        [{"id": f"doc_{i}", "@search.reranker_score": 3.0} for i in range(50)]
    )
    with patch.object(p._rerank_client, "search", AsyncMock(return_value=async_iter_mock)):
        out = await p._apply_semantic_ranking("q", fused)

    assert len(out) == 55
    assert out[0]["_final_score"] == 3.0
    assert out[50]["id"] == "doc_50"
    assert "_final_score" not in out[50]


@pytest.mark.asyncio
async def test_apply_semantic_ranking_edge_and_fallback(config: SearchConfig) -> None:
    """Test semantic ranking edge cases and fallback behavior.

    Verifies handling of empty inputs, missing ID fields, and API errors
    by falling back to fused scores when reranking fails.
    """
    r, f, g = MagicMock(), MagicMock(), MagicMock()
    p = AdvancedSearchPipeline(config, r, f, g)

    # empty input
    assert await p._apply_semantic_ranking("q", []) == []

    # missing id field in config
    p._config = config.model_copy(update={"id_field": "nope"})
    fused: list[dict[str, Any]] = [{"id": "A"}]
    assert await p._apply_semantic_ranking("q", fused) == fused

    # API error fallback
    p._config = config.model_copy(update={"id_field": "id"})
    fused_with_score = [{"id": "A", "_fused_score": 0.9}]

    async def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("x")

    with patch.object(p._rerank_client, "search", AsyncMock(side_effect=boom)):
        out = await p._apply_semantic_ranking("q", fused_with_score)
    assert out[0]["_final_score"] == 0.9


def test_clean_sources_removes_internal(config: SearchConfig) -> None:
    """Test that clean_sources removes internal metadata fields from results.

    Verifies that intermediate scoring fields and Azure-specific metadata
    are removed while preserving final scores and retrieval types.
    """
    r, f, g = MagicMock(), MagicMock(), MagicMock()
    p = AdvancedSearchPipeline(config, r, f, g)
    rows = [
        {
            config.id_field: "1",
            config.content_field: "C",
            "_retrieval_score": 1.0,
            "_normalized_score": 1.0,
            "_fused_score": 0.8,
            "_final_score": 3.3,
            "@search.score": 1.0,
            "@search.reranker_score": 3.3,
            "@search.captions": "cap",
            config.vector_field: [0.1],
            "_retrieval_type": "hybrid",
        }
    ]
    out = p._clean_sources(rows)
    assert out[0][config.id_field] == "1"
    assert out[0]["_final_score"] == 3.3
    assert out[0]["_retrieval_type"] == "hybrid"
    for k in (
        "_retrieval_score",
        "_normalized_score",
        "_fused_score",
        "@search.score",
        "@search.reranker_score",
        "@search.captions",
        cast(str, config.vector_field),
    ):
        assert k not in out[0]


@pytest.mark.asyncio
async def test_get_answer_paths(config: SearchConfig) -> None:
    """Test get_answer execution paths with and without semantic ranking.

    Verifies answer generation works with semantic ranking enabled, handles
    empty results gracefully, and processes non-semantic paths correctly.
    """
    cfg = config.model_copy(update={"enable_answer_generation": True})

    r = MagicMock()
    f = MagicMock()
    g = MagicMock()

    p = AdvancedSearchPipeline(cfg, r, f, g)

    # happy path with semantic
    r.search_lexical = AsyncMock(return_value=[{"id": "L1"}])
    r.search_vector = AsyncMock(return_value=[{"id": "V1"}])
    f.fuse = AsyncMock(return_value=[{"id": "S1", "_fused_score": 0.4, "vector": [0.1]}])
    g.generate = AsyncMock(return_value="final")
    with patch.object(
        p,
        "_apply_semantic_ranking",
        new=AsyncMock(
            return_value=[{"id": "S1", "_final_score": 3.0, "content": "C", "vector": [0.1]}]
        ),
    ):
        out = await p.get_answer("q")
    assert out["answer"] == "final"
    assert "vector" not in out["source_chunks"][0]

    # no results -> friendly message
    with patch.object(p, "_apply_semantic_ranking", new=AsyncMock(return_value=[])):
        out2 = await p.get_answer("q")
    assert "could not find" in out2["answer"].lower()

    # no semantic path
    cfg2 = cfg.model_copy(update={"use_semantic_ranking": False})
    p2 = AdvancedSearchPipeline(cfg2, r, f, g)
    r.search_lexical = AsyncMock(return_value=[{"id": "L"}])
    r.search_vector = AsyncMock(return_value=[{"id": "V"}])
    f.fuse = AsyncMock(return_value=[{"id": "F", "_fused_score": 0.4}])
    g.generate = AsyncMock(return_value="ans")
    out3 = await p2.get_answer("q")
    assert out3["answer"] == "ans"
    assert out3["source_chunks"][0]["_final_score"] == 0.4


@pytest.mark.asyncio
async def test_pipeline_close(config: SearchConfig) -> None:
    """Test that pipeline close properly closes all component resources.

    Verifies that the pipeline's close method calls close on the rerank
    client, retriever, fuser, and generator components.
    """
    r, f, g = MagicMock(), MagicMock(), MagicMock()
    r.close = AsyncMock()
    f.close = AsyncMock()
    g.close = AsyncMock()

    p = AdvancedSearchPipeline(config, r, f, g)
    with patch.object(p._rerank_client, "close", new_callable=AsyncMock) as mock_close:
        await p.close()
        mock_close.assert_awaited()
        r.close.assert_awaited()
        f.close.assert_awaited()
        g.close.assert_awaited()
