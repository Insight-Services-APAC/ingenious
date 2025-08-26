"""Tests an Azure Search pipeline edge case with semantic reranking.

This module contains a regression test to ensure that the semantic reranking
logic correctly handles document IDs containing commas. Such IDs can conflict
with the `search.in()` filter syntax used in Azure Cognitive Search,
potentially causing documents to be dropped.

The primary test simulates a scenario where the semantic reranking call returns
no results for a comma-containing ID, and verifies that the original document
is preserved in the final output.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest

if TYPE_CHECKING:
    from pytest import MonkeyPatch

# ⬇️ Adjust this import to your project layout if needed
# The target module may not have type stubs, hence the ignore.
PipelineMod = pytest.importorskip("ingenious.services.azure_search.pipeline")
AdvancedSearchPipeline = PipelineMod.AdvancedSearchPipeline


@pytest.mark.asyncio
async def test_semantic_rerank_preserves_docs_when_id_has_comma(
    monkeypatch: MonkeyPatch,
) -> None:
    """Verify docs with comma-containing IDs are preserved during reranking.

    This test guards against a regression where a document ID containing a comma
    (e.g., "doc,1") would be dropped if the semantic reranker failed to return
    it. This can happen if the ID is misinterpreted by the `search.in()` filter.
    The test asserts that the pipeline falls back to using the original,
    un-reranked document in such cases, preventing data loss.
    """
    # Make a pipeline instance without running its __init__ to isolate the method.
    pipeline: AdvancedSearchPipeline = AdvancedSearchPipeline.__new__(
        AdvancedSearchPipeline
    )

    # Force the internal semantic rerank call to yield no results, simulating
    # a scenario where the filter excluded the comma-containing ID.
    monkeypatch.setattr(pipeline, "_semantic_rerank", AsyncMock(return_value=[]))

    # Set a generous cap so test data isn't truncated by internal limits.
    setattr(pipeline, "_MAX_RERANK", 50)

    fused: list[dict[str, Any]] = [
        {
            "id": "doc,1",  # <- the problematic ID with commas
            "content": "alpha",
            "_fused_score": 0.72,
        },
        {
            "id": "doc-2",
            "content": "beta",
            "_fused_score": 0.55,
        },
    ]

    # Directly invoke the method under test to focus on the merge behavior.
    # The `attr-defined` ignore is necessary because we bypassed `__init__`,
    # so mypy cannot statically determine the method's existence.
    final: list[dict[str, Any]] = await pipeline._apply_semantic_ranking(  # type: ignore[attr-defined]
        query="any query",
        fused_results=fused,
        top_n_final=2,
    )

    # The doc with a comma in its ID must still be present in the final list.
    final_ids: list[Any] = [d.get("id") for d in final]
    assert "doc,1" in final_ids, "fused doc with comma in ID should be preserved"

    # And it should be the unchanged fused doc (score kept, not mutated).
    preserved: dict[str, Any] = next(d for d in final if d["id"] == "doc,1")
    assert preserved.get("_fused_score") == 0.72
