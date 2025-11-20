"""Concurrency cancellation now tested at the pipeline (single-source) level.

If one L1 branch fails, the sibling branch must be cancelled promptly.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, NoReturn

import pytest

from ingenious.services.azure_search.components.pipeline import AdvancedSearchPipeline
from ingenious.services.azure_search.config import SearchConfig


@pytest.mark.asyncio
@pytest.mark.parametrize("failing_branch", ["vector", "lexical"])
async def test_l1_other_branch_cancelled_on_failure(
    failing_branch: str, config: SearchConfig
) -> None:
    """Test that L1 search cancels the other branch when one branch fails.

    Verifies that when either vector or lexical search fails, the concurrent
    search branch is properly cancelled to avoid resource waste.
    """
    cancelled: asyncio.Event = asyncio.Event()

    async def slow_sleeping_search(_q: str) -> NoReturn:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        pytest.fail("slow_sleeping_search completed instead of being cancelled.")

    async def fast_failing_search(_q: str) -> NoReturn:
        raise TimeoutError("simulated L1 failure")

    # Stub components: only retriever is used before the error
    retriever = SimpleNamespace()
    if failing_branch == "vector":
        retriever.search_vector = fast_failing_search
        retriever.search_lexical = slow_sleeping_search
    else:
        retriever.search_vector = slow_sleeping_search
        retriever.search_lexical = fast_failing_search

    async def _should_not_run(*_a: Any, **_k: Any) -> NoReturn:
        pytest.fail("fuser.fuse should not be reached when an L1 branch fails")

    fuser = SimpleNamespace(fuse=_should_not_run)

    p = AdvancedSearchPipeline(config, retriever, fuser)

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(p.retrieve("q", top_k=1), timeout=2.0)

    await asyncio.wait_for(cancelled.wait(), timeout=0.5)
