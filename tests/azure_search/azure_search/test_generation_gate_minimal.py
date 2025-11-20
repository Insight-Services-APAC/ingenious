"""Tests the AdvancedSearchPipeline and its construction factory.

This module contains unit and integration tests for the core RAG pipeline logic
defined in `ingenious.services.azure_search.components.pipeline`. It verifies
the behavior of the `AdvancedSearchPipeline` class and the
`build_search_pipeline` factory function, ensuring correct data flow,
component lifecycle (construction, closing), and error handling under
controlled conditions using stub implementations.

Usage:
- Run with pytest; async tests are marked with `@pytest.mark.asyncio`.
- Stubs/spies avoid network calls and make behavior deterministic.
- Entry points: build_* tests and get_answer* tests below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from pytest import MonkeyPatch

from ingenious.services.azure_search.components.pipeline import (
    AdvancedSearchPipeline,
    build_search_pipeline,
)
from ingenious.services.retrieval.errors import GenerationDisabledError

if TYPE_CHECKING:
    # Type-only import to satisfy Ruff/mypy without importing at runtime.
    # Adjust the path below if SearchConfig resides elsewhere.
    from ingenious.services.azure_search.config import SearchConfig

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

EXPECTED_EMPTY_QUERY_MSG = "Please enter a question so I can search the knowledge base."

# ──────────────────────────────────────────────────────────────────────────────
# Test stubs
# ──────────────────────────────────────────────────────────────────────────────


class StubRetriever:
    """A test double for the AzureSearchRetriever.

    This class provides predictable, hardcoded responses for search methods,
    allowing tests to focus on pipeline logic without actual network calls.
    """

    def __init__(self, *_: Any, **__: Any) -> None:
        """Initialize the stub, ignoring all arguments for simplicity."""
        self.closed: bool = False

    async def search_lexical(self, query: str) -> list[dict[str, Any]]:
        """Simulate a lexical search, returning a fixed result.

        This method mimics the output of a lexical search component to provide
        consistent input for downstream pipeline stages like fusion.
        """
        return [{"id": "L1", "content": "lex-1", "@search.score": 0.2}]

    async def search_vector(self, query: str) -> list[dict[str, Any]]:
        """Simulate a vector search, returning a fixed result.

        This method mimics the output of a vector search component, enabling
        tests for hybrid retrieval scenarios.
        """
        return [{"id": "V1", "content": "vec-1", "@search.score": 0.3}]

    async def close(self) -> None:
        """Mark the stub as closed to verify resource cleanup logic.

        This allows tests to confirm that the pipeline's `close` method
        correctly propagates the call to its components.
        """
        self.closed = True


class StubFuser:
    """A test double for the DynamicRankFuser.

    This class simulates the result-merging stage of the pipeline with a
    constant output, ensuring predictable data flow to the generator.
    """

    def __init__(self, *_: Any, **__: Any) -> None:
        """Initialize the stub, ignoring all arguments."""
        self.closed: bool = False

    async def fuse(
        self,
        query: str,
        lexical_results: list[dict[str, Any]],
        vector_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Simulate result fusion, returning a fixed list of documents.

        The returned data is constant to provide a predictable input for
        downstream components like the answer generator.
        """
        docs: list[dict[str, Any]] = [
            {
                "id": "A",
                "content": "A",
                "_fused_score": 0.9,
                "_retrieval_type": "hybrid",
                "vector": [0.1, 0.2],
            },
            {
                "id": "B",
                "content": "B",
                "_fused_score": 0.8,
                "_retrieval_type": "hybrid",
            },
            {
                "id": "C",
                "content": "C",
                "_fused_score": 0.5,
                "_retrieval_type": "hybrid",
            },
            {
                "id": "D",
                "content": "D",
                "_fused_score": 0.1,
                "_retrieval_type": "hybrid",
            },
        ]
        return docs

    async def close(self) -> None:
        """Mark the stub as closed to verify cleanup logic.

        This supports testing the pipeline's resource management behavior.
        """
        self.closed = True


class EmptyFuser(StubFuser):
    """A fuser stub that returns no results.

    This class is used to test the pipeline's behavior when no relevant
    documents are found after the retrieval and fusion stages.
    """

    async def fuse(self, *_: Any, **__: Any) -> list[dict[str, Any]]:
        """Simulate a fusion that finds no relevant documents."""
        return []


class SpyAnswerGen:
    """A test double for the AnswerGenerator that spies on calls.

    This class helps verify that the pipeline correctly invokes the answer
    generation step and tracks component instantiation.
    """

    constructed: int = 0

    def __init__(self, *_: Any, **__: Any) -> None:
        """Initialize the spy and increment the global construction counter.

        This allows tests to check how many times the generator is instantiated.
        """
        SpyAnswerGen.constructed += 1
        self.generate_calls: int = 0
        self.closed: bool = False

    async def generate(self, query: str, chunks: list[dict[str, Any]]) -> str:
        """Simulate answer generation, record the call, and return a fixed answer.

        This method allows tests to confirm that the generator was called
        with the expected inputs from the previous pipeline stages.
        """
        self.generate_calls += 1
        return "GEN ANSWER"

    async def close(self) -> None:
        """Mark the spy as closed to verify cleanup logic.

        This supports testing the pipeline's resource management behavior.
        """
        self.closed = True


class BoomAnswerGen(SpyAnswerGen):
    """An answer generator stub that always raises an error.

    This class is used to test the pipeline's error handling capabilities
    when the final generation stage fails.
    """

    async def generate(self, *_: Any, **__: Any) -> str:
        """Simulate a failure during the answer generation process."""
        raise RuntimeError("boom")


class StubRerankClient:
    """A test double for the rerank client.

    This class stands in for a client used in semantic reranking, allowing
    tests to verify its lifecycle management within the pipeline.
    """

    def __init__(self) -> None:
        """Initialize the stub, setting its initial state."""
        self.closed: bool = False

    async def close(self) -> None:
        """Mark the stub as closed to verify cleanup logic.

        This supports testing the pipeline's resource management behavior.
        """
        self.closed = True


# ──────────────────────────────────────────────────────────────────────────────
# build_search_pipeline() construction behavior
# ──────────────────────────────────────────────────────────────────────────────


def test_build_pipeline_generation_disabled_no_generator(
    monkeypatch: MonkeyPatch, config: Any
) -> None:
    """Verify builder returns a pipeline with no generator when disabled.

    This test ensures the 'enable_answer_generation' config flag correctly
    prevents the instantiation of the AnswerGenerator component, which is
    important for resource management and conditional logic.
    """
    from ingenious.services.azure_search.components import pipeline as P

    monkeypatch.setattr(P, "AzureSearchRetriever", StubRetriever)
    monkeypatch.setattr(P, "DynamicRankFuser", StubFuser)
    monkeypatch.setattr(P, "AnswerGenerator", SpyAnswerGen)

    cfg = config.copy(update={"enable_answer_generation": False})
    pipe = build_search_pipeline(cfg)

    assert isinstance(pipe, AdvancedSearchPipeline)
    assert pipe.answer_generator is None
    assert SpyAnswerGen.constructed == 0


def test_build_pipeline_generation_enabled_constructs_generator(
    monkeypatch: MonkeyPatch, config: Any
) -> None:
    """Verify the builder constructs and attaches the generator when enabled.

    This test confirms that the factory correctly interprets the configuration
    to instantiate and include all necessary components for a full RAG workflow.
    """
    from ingenious.services.azure_search.components import pipeline as P

    SpyAnswerGen.constructed = 0
    monkeypatch.setattr(P, "AzureSearchRetriever", StubRetriever)
    monkeypatch.setattr(P, "DynamicRankFuser", StubFuser)
    monkeypatch.setattr(P, "AnswerGenerator", SpyAnswerGen)

    cfg = config.copy(update={"enable_answer_generation": True})
    pipe = build_search_pipeline(cfg)

    assert pipe.answer_generator is not None
    assert SpyAnswerGen.constructed == 1


# ──────────────────────────────────────────────────────────────────────────────
# get_answer() runtime behavior
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_answer_generation_enabled_calls_generator(
    config_no_semantic: Any,
) -> None:
    """Verify get_answer calls the generator and includes its response.

    This test checks the happy-path data flow, ensuring that when answer
    generation is enabled, the pipeline passes the fused chunks to the
    generator and includes its output in the final response.
    """
    cfg = config_no_semantic.copy(update={"enable_answer_generation": True, "top_n_final": 2})
    gen = SpyAnswerGen(cfg)

    pipe = AdvancedSearchPipeline(
        config=cfg,
        retriever=StubRetriever(cfg),
        fuser=StubFuser(cfg),
        answer_generator=gen,
        rerank_client=StubRerankClient(),
    )

    res = await pipe.get_answer("q")
    assert res["answer"] == "GEN ANSWER"
    assert len(res["source_chunks"]) == 2
    assert gen.generate_calls == 1


@pytest.mark.asyncio
async def test_get_answer_generation_disabled_raises_and_performs_no_io(
    config_no_semantic: Any,
) -> None:
    """Verify get_answer raises an error and performs no I/O when disabled.

    This test confirms the pipeline's fail-fast behavior. It ensures that
    calling `get_answer` when generation is disabled immediately raises a
    specific error without making costly network calls.
    """
    cfg = config_no_semantic.copy(update={"enable_answer_generation": False, "top_n_final": 3})

    retriever = StubRetriever(cfg)
    fuser = StubFuser(cfg)
    reranker = StubRerankClient()

    with (
        patch.object(retriever, "search_lexical") as lex_spy,
        patch.object(retriever, "search_vector") as vec_spy,
        patch.object(fuser, "fuse") as fuse_spy,
    ):
        pipe = AdvancedSearchPipeline(
            config=cfg,
            retriever=retriever,
            fuser=fuser,
            answer_generator=None,  # generation off
            rerank_client=reranker,
        )

        with pytest.raises(GenerationDisabledError):
            await pipe.get_answer("q")

        lex_spy.assert_not_called()
        vec_spy.assert_not_called()
        fuse_spy.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "empty_query",
    [
        "",  # Empty string
        "   ",  # Whitespace only
        " \t \n ",  # Mixed whitespace
    ],
)
async def test_get_answer_empty_query_short_circuits_without_io(
    empty_query: str, config_no_semantic: Any
) -> None:
    """Verify get_answer returns a default response for empty queries and skips I/O.

    This test checks the input validation logic. It ensures that empty or
    whitespace-only queries are handled gracefully with a default message
    and do not trigger any downstream processing, saving resources.
    """
    # Generation must be enabled to ensure we are testing the query check,
    # not the generation-disabled check.
    cfg = config_no_semantic.copy(update={"enable_answer_generation": True})

    retriever = StubRetriever(cfg)
    fuser = StubFuser(cfg)
    gen = SpyAnswerGen(cfg)
    reranker = StubRerankClient()

    with (
        patch.object(retriever, "search_lexical") as lex_spy,
        patch.object(retriever, "search_vector") as vec_spy,
        patch.object(fuser, "fuse") as fuse_spy,
        patch.object(gen, "generate") as gen_spy,
    ):
        pipe = AdvancedSearchPipeline(
            config=cfg,
            retriever=retriever,
            fuser=fuser,
            answer_generator=gen,
            rerank_client=reranker,
        )

        # Execute the method with the empty query
        result = await pipe.get_answer(empty_query)

        # 1. Assert the expected short-circuit response
        assert result["answer"] == EXPECTED_EMPTY_QUERY_MSG
        assert result["source_chunks"] == []

        # 2. Assert that no downstream components were ever called
        lex_spy.assert_not_called()
        vec_spy.assert_not_called()
        fuse_spy.assert_not_called()
        gen_spy.assert_not_called()


@pytest.mark.asyncio
async def test_get_answer_generation_error_bubbles_as_runtime_error(
    config_no_semantic: "SearchConfig",
) -> None:
    """Check that a generator failure propagates from `get_answer`."""

    class StubRetriever:
        """Retriever stub returning a single chunk."""

        async def search_lexical(self, _: str) -> list[dict[str, str]]:
            """No-op; unused in this path."""
            return []

        async def search_vector(self, _: str) -> list[dict[str, str]]:
            """No-op; unused in this path."""
            return []

        async def close(self) -> None:
            """No-op."""
            return None

    class StubFuser:
        """Fuser stub that returns one fused result."""

        async def fuse(self, *_a: object, **_k: object) -> list[dict[str, str]]:
            """Return one minimal doc."""
            return [{"id": "1", "content": "c", "_final_score": 1.0}]

        async def close(self) -> None:
            """No-op."""
            return None

    class BoomAnswerGen:
        """Answer generator stub that raises on use."""

        async def generate(self, *_a: object, **_k: object) -> str:
            """Always raise to simulate LLM failure."""
            raise RuntimeError("oops")

        async def close(self) -> None:
            """No-op."""
            return None

    # ✅ Enable generation for this test case
    cfg = config_no_semantic.copy(update={"enable_answer_generation": True})

    p = AdvancedSearchPipeline(
        config=cfg,
        retriever=StubRetriever(),  # type: ignore[arg-type]
        fuser=StubFuser(),  # type: ignore[arg-type]
        answer_generator=BoomAnswerGen(),
        rerank_client=None,
    )

    with pytest.raises(RuntimeError):
        await p.get_answer("q")


@pytest.mark.asyncio
async def test_pipeline_close_safely_handles_none_generator(
    config_no_semantic: Any,
) -> None:
    """Verify close() calls close on all components and handles a null generator.

    This test confirms that the pipeline's cleanup logic correctly calls the
    `close` method on each of its components and does not fail if the
    answer generator is `None`, which is a valid state.
    """
    cfg = config_no_semantic.copy(update={"enable_answer_generation": False})
    retr = StubRetriever(cfg)
    fus = StubFuser(cfg)
    rr = StubRerankClient()

    pipe = AdvancedSearchPipeline(
        config=cfg,
        retriever=retr,
        fuser=fus,
        answer_generator=None,
        rerank_client=rr,
    )

    await pipe.close()
    assert retr.closed is True
    assert fus.closed is True
    assert rr.closed is True
