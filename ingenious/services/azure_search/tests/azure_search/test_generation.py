"""Tests the AnswerGenerator for RAG response synthesis.

This module provides unit tests for the AnswerGenerator component, which is
responsible for synthesizing a final answer from a user query and retrieved
context chunks using an LLM.

Key behaviors tested include:
- Correct context formatting from source documents.
- Successful answer generation via a mocked LLM client.
- Graceful handling of edge cases like empty context or LLM exceptions.
- Proper resource management (client closing).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest

from ingenious.services.azure_search.components.generation import (
    DEFAULT_RAG_PROMPT,
    AnswerGenerator,
)
from ingenious.services.azure_search.config import SearchConfig

if TYPE_CHECKING:
    from collections.abc import Generator

    from pytest import MonkeyPatch


@pytest.fixture
def generator(config: SearchConfig) -> Generator[AnswerGenerator, None, None]:
    """Provides an AnswerGenerator with a mocked LLM client.

    This fixture instantiates an AnswerGenerator and replaces its internal
    LLM client with an AsyncMock to simulate API calls without actual network
    requests. It also ensures the client's lifecycle is managed correctly
    for testing purposes.

    Args:
        config: The search configuration fixture.

    Yields:
        An AnswerGenerator instance ready for testing.
    """
    gen = AnswerGenerator(config)
    mock_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock())),
        close=AsyncMock(),
    )
    # Patch the instance to inject a mock client and control ownership,
    # ensuring test isolation and predictable behavior.
    with (
        patch.object(gen, "_llm_client", mock_client),
        patch.object(gen, "_owns_llm", True),
    ):
        yield gen


def test_generator_init_and_prompt(generator: AnswerGenerator) -> None:
    """Tests that the generator initializes with the default prompt.

    This ensures that the component is configured with the correct RAG
    prompt template out-of-the-box and that the internal client attribute
    is present.
    """
    assert generator.rag_prompt_template == DEFAULT_RAG_PROMPT
    assert hasattr(generator, "_llm_client")


def test_format_context(generator: AnswerGenerator, config: SearchConfig) -> None:
    """Tests that context formatting enumerates and separates sources correctly.

    The LLM requires context to be clearly delineated. This test verifies
    that source documents are formatted with unique identifiers and separators
    to aid the model in citation and comprehension.
    """
    chunks: list[dict[str, Any]] = [
        {"id": "1", config.content_field: "A."},
        {"id": "2", config.content_field: "B."},
    ]
    out: str = generator._format_context(chunks)
    assert "[Source 1]" in out and "A." in out
    assert "[Source 2]" in out and "B." in out
    assert "\n---\n" in out


def test_format_context_missing_content(generator: AnswerGenerator) -> None:
    """Tests that missing content fields are handled gracefully.

    If a source document is missing the expected content field, the formatting
    logic should substitute a placeholder ('N/A') instead of raising an error,
    ensuring robustness.
    """
    out: str = generator._format_context([{"id": "1"}])
    assert "N/A" in out


@pytest.mark.asyncio
async def test_generate_success(
    generator: AnswerGenerator, config: SearchConfig, monkeypatch: MonkeyPatch
) -> None:
    """Tests the successful answer generation path.

    This test ensures that when provided with a query and context, the generator
    correctly calls the underlying LLM client and returns the content of the
    model's response.
    """
    client: Any = generator._llm_client
    # Define a realistic, nested mock response from the LLM.
    mock_create_method = AsyncMock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content="Answer [Source 1]"))
            ]
        )
    )
    monkeypatch.setattr(client.chat.completions, "create", mock_create_method)

    ans: str = await generator.generate("Q", [{"id": "1", config.content_field: "C"}])

    assert ans.startswith("Answer")
    mock_create_method.assert_awaited()


@pytest.mark.asyncio
async def test_generate_empty_short_circuit(generator: AnswerGenerator) -> None:
    """Tests that generation is short-circuited if context is empty.

    To save costs and avoid nonsensical LLM calls, the generator should not
    contact the model if there are no context documents. It should instead
    return a graceful, predefined message.
    """
    ans: str = await generator.generate("Q", [])
    assert "could not find any relevant information" in ans.lower()

    # The mock LLM client is created in the `generator` fixture.
    # We must verify it was NOT called.
    llm_mock: Any = generator._llm_client
    llm_mock.chat.completions.create.assert_not_called()


@pytest.mark.asyncio
async def test_generate_exception(
    generator: AnswerGenerator, config: SearchConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Raise on LLM error instead of returning a fallback string."""

    async def boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("oops")

    # Ensure awaited call is awaitable
    monkeypatch.setattr(
        generator._llm_client.chat.completions, "create", boom, raising=True
    )

    with pytest.raises(RuntimeError):
        await generator.generate("q", [{config.content_field: "x"}])


@pytest.mark.asyncio
async def test_generator_close(generator: AnswerGenerator) -> None:
    """Tests that the generator properly closes its underlying client.

    To ensure proper resource management, the generator's close method must
    propagate the call to its internal, owned LLM client. This test verifies
    that the client's `close` method is awaited.
    """
    await generator.close()

    # The mock LLM client is created in the `generator` fixture.
    llm_mock: Any = generator._llm_client
    llm_mock.close.assert_awaited()
