"""Test edge cases for the Knowledge Base agent's streaming response flow.

This module contains tests for specific, less common scenarios in the
`get_streaming_conversation_response` method of the `ConversationFlow`. It focuses
on ensuring robust behavior when the underlying `autogen` agent produces
unusual output streams, such as yielding a `TaskResult` object after partial
content, or when token counting mechanisms fail.

The tests use `pytest` and extensive `monkeypatch`ing to isolate the flow from
external dependencies (like LLMs and tokenizers) and simulate these edge cases.
"""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, NoReturn

import pytest

import ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent.knowledge_base_agent as kb

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Iterator
    from pathlib import Path

    from pytest import MonkeyPatch

    from ingenious.models.chat import ChatResponseChunk


class DummyLLMClient:
    """A mock LLM client that does nothing."""

    async def close(self) -> None:
        """Simulate closing the client connection."""
        pass


class AcceptingLogHandler:
    """A mock log handler that accepts and discards all records."""

    def __init__(self, *a: Any, **k: Any) -> None:
        """Initialize the handler, accepting any arguments."""
        pass

    def emit(self, r: Any) -> None:
        """Accept and discard any log record."""
        pass


@pytest.fixture(autouse=True)
def _patch_basics(monkeypatch: MonkeyPatch) -> Iterator[None]:
    """Patch core dependencies to isolate the ConversationFlow for testing.

    This pytest fixture runs for every test, replacing external dependencies
    like the `LLMUsageTracker`, Azure clients, and parts of `autogen` with
    minimal, controllable fakes. This ensures tests are fast, repeatable, and
    focused only on the logic within the `ConversationFlow` streaming method.
    """
    # autogen_core presence
    core = types.ModuleType("autogen_core")
    core.EVENT_LOGGER_NAME = "autogen"

    class _CT: ...

    core.CancellationToken = _CT
    monkeypatch.setitem(sys.modules, "autogen_core", core)
    tools = types.ModuleType("autogen_core.tools")

    class _FT: ...

    tools.FunctionTool = _FT
    monkeypatch.setitem(sys.modules, "autogen_core.tools", tools)
    # minimal messages module for constructor parity (not used by streaming path here)
    agents = types.ModuleType("autogen_agentchat.agents")
    monkeypatch.setitem(sys.modules, "autogen_agentchat.agents", agents)

    monkeypatch.setattr(kb, "LLMUsageTracker", AcceptingLogHandler, raising=False)
    monkeypatch.setattr(kb, "LLMUsageTracker", AcceptingLogHandler, raising=False)
    # Patch new client factory
    monkeypatch.setattr(
        kb,
        "AzureClientFactory",
        SimpleNamespace(create_openai_chat_completion_client=lambda _cfg: DummyLLMClient()),
    )
    yield


@pytest.mark.asyncio
async def test_stream_includes_taskresult_final_flush_content(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """Verify final message from a TaskResult-like object is streamed.

    This test ensures that if the underlying `autogen` agent stream yields partial
    content and then terminates with a `TaskResult`-like object containing final
    messages, the content of the final message is correctly extracted and yielded
    to the consumer as a content chunk. This simulates `autogen`'s behavior of
    flushing final state at the end of a stream.
    """

    # AssistantAgent.run_stream that yields a content chunk then a TaskResult-like object with final messages
    class FakeAgent:
        """A mock AssistantAgent that yields partial content then a final message object."""

        def __init__(self, *a: Any, **k: Any) -> None:
            """Initialize the agent, accepting any arguments."""
            pass

        def run_stream(
            self, task: Any, cancellation_token: Any = None
        ) -> AsyncGenerator[Any, None]:
            """Simulate a streaming run yielding partial content and a final result object."""

            async def _gen() -> AsyncGenerator[Any, None]:
                """Generate the fake stream data."""
                yield SimpleNamespace(content="partial", usage=None)

                class TaskResultLike:
                    """A mock result object mimicking autogen's TaskResult."""

                    def __init__(self) -> None:
                        """Initialize with a list of mock messages."""
                        self.messages = [
                            SimpleNamespace(content="MID"),
                            SimpleNamespace(content="FINAL"),
                        ]

                yield TaskResultLike()

            return _gen()

    monkeypatch.setattr(kb, "AssistantAgent", FakeAgent)

    flow: kb.ConversationFlow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    flow._config = SimpleNamespace(models=[SimpleNamespace(model="gpt-5")])
    flow._chat_service = None
    flow._memory_path = str(tmp_path)

    from ingenious.models.chat import ChatRequest

    chunks: list[ChatResponseChunk] = [
        c async for c in flow.get_streaming_conversation_response(ChatRequest(user_prompt="q"))
    ]

    contents: list[str | None] = [c.content for c in chunks if c.chunk_type == "content"]
    # "FINAL" should be appended via TaskResult flush restoration
    assert any(c == "FINAL" for c in contents)
    # A final chunk must be present
    assert chunks[-1].chunk_type == "final"


@pytest.mark.asyncio
async def test_stream_emits_token_count_when_usage_missing_and_counter_errors(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """Ensure a fallback token count is emitted if usage data and token counting fail.

    This test verifies the system's resilience. If the LLM stream does not report
    token usage and the internal utility for counting tokens also raises an
    error, the flow should still emit a `token_count` chunk with a non-zero
    (estimated) value rather than failing or omitting it.
    """

    # AssistantAgent.run_stream emits only content; no usage reported
    class FakeAgent:
        """A mock AssistantAgent that yields only content without usage data."""

        def __init__(self, *a: Any, **k: Any) -> None:
            """Initialize the agent, accepting any arguments."""
            pass

        def run_stream(
            self, task: Any, cancellation_token: Any = None
        ) -> AsyncGenerator[Any, None]:
            """Simulate a streaming run that yields content but no usage info."""

            async def _gen() -> AsyncGenerator[Any, None]:
                """Generate the fake stream data."""
                yield SimpleNamespace(content="some streamed text", usage=None)

            return _gen()

    monkeypatch.setattr(kb, "AssistantAgent", FakeAgent)

    # Token counter import succeeds but function raises
    tc = types.ModuleType("ingenious.utils.token_counter")

    def _boom(msgs: Any, model: Any) -> NoReturn:
        """A mock token counter that always fails."""
        raise RuntimeError("counter failed")

    tc.num_tokens_from_messages = _boom
    monkeypatch.setitem(sys.modules, "ingenious.utils.token_counter", tc)

    flow: kb.ConversationFlow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    flow._config = SimpleNamespace(models=[SimpleNamespace(model="gpt-5")])
    flow._chat_service = None
    flow._memory_path = str(tmp_path)

    from ingenious.models.chat import ChatRequest

    chunks: list[ChatResponseChunk] = [
        c async for c in flow.get_streaming_conversation_response(ChatRequest(user_prompt="hello"))
    ]
    # There must be a token_count chunk with non-zero token_count, then a final
    tc_chunks: list[ChatResponseChunk] = [c for c in chunks if c.chunk_type == "token_count"]
    assert tc_chunks and tc_chunks[-1].token_count > 0
    assert chunks[-1].chunk_type == "final"
