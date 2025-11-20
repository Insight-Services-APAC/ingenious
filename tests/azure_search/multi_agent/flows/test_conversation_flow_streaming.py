"""Tests for the streaming response generation of the ConversationFlow.

This module contains pytest unit tests for the `get_streaming_conversation_response`
method in the `knowledge_base_agent.ConversationFlow` class. It focuses on
verifying the correctness of the streaming output under various conditions,
including happy paths, tool usage, error handling, and token counting fallbacks.

To isolate the streaming logic, all external dependencies are heavily mocked.
This includes the Azure OpenAI client, the underlying `AssistantAgent`, memory
management services, and token counting utilities. A primary fixture, `flow_fixture`,
provides a pre-configured `ConversationFlow` instance and a `controls` object
that allows tests to inject specific event sequences into the mocked agent stream.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest

# Import the module under test; adjust the module name here if needed.
import ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent.knowledge_base_agent as kba

if TYPE_CHECKING:
    from pathlib import Path


# -------------------------
# Helpers for fake stream messages
# -------------------------
class _Usage:
    """A simple helper class to mimic token usage data structures."""

    def __init__(
        self, total_tokens: int | None = None, completion_tokens: int | None = None
    ) -> None:
        """Initialize the usage object."""
        self.total_tokens = total_tokens
        self.completion_tokens = completion_tokens


def msg_text(text: str) -> SimpleNamespace:
    """Create a simple message object with a .content attribute."""
    return SimpleNamespace(content=text)


def msg_usage(total: int, completion: int) -> SimpleNamespace:
    """Create a message object carrying token usage."""
    return SimpleNamespace(usage=_Usage(total_tokens=total, completion_tokens=completion))


class ToolCallDelta:
    """A marker class whose name is used to detect tool events in the stream."""

    pass


class TaskResultMock:
    """A marker class whose name is used to detect the terminal result from the agent."""

    def __init__(self, final_text: str) -> None:
        """Initialize the mock with the final text content."""
        self.messages = [
            SimpleNamespace(content="ignored"),
            SimpleNamespace(content=final_text),
        ]


# -------------------------
# Fixture: fresh ConversationFlow with baseline mocks
# -------------------------
@pytest.fixture
def flow_fixture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[kba.ConversationFlow, SimpleNamespace]:
    """Provide a fresh ConversationFlow instance with comprehensive baseline mocks.

    This fixture is the core setup for all tests in this module. It patches
    all major dependencies of the `ConversationFlow` to ensure that tests are
    isolated and deterministic.

    Patches include:
    - `create_aoai_chat_completion_client_from_config`: Returns a mock async client.
    - `AssistantAgent`: Replaced with a dummy class whose `run_stream` method
      yields items controlled by the test.
    - `get_memory_manager`: Replaced with a no-op stub to prevent side-effects.
    - Internal helper methods (`_build_memory_context`, etc.) are patched to
      return deterministic default values.

    Returns:
        A tuple containing the configured `ConversationFlow` instance and a
        `controls` namespace object. The `controls` object allows tests to
        dynamically set the items yielded by the stream (`stream_items`) and
        inspect mock state (`client_closed`, `assistant_instances`).
    """

    # --- Minimal parent service ------------------------------------------------
    class _Repo:
        """A mock repository for chat history operations."""

        async def get_thread_messages(self, thread_id: str) -> list[Any]:
            """Return an empty list of messages."""
            return []

        async def add_message(self, *args: Any, **kwargs: Any) -> str:
            """Return a dummy message ID."""
            return "msg-id"

        async def add_memory(self, *args: Any, **kwargs: Any) -> str:
            """Return a dummy memory ID."""
            return "mem-id"

    class _ParentService:
        """A mock parent service containing necessary configuration."""

        def __init__(self, mem_root: str) -> None:
            """Initialize the mock service with minimal config."""
            # Must match what IConversationFlow.__init__ reads
            self.config = SimpleNamespace(
                models=[SimpleNamespace(model="gpt-test-model")],
                chat_history=SimpleNamespace(memory_path=mem_root),
            )
            self.chat_history_repository = _Repo()

    mem_root = str(tmp_path / "mem")
    parent = _ParentService(mem_root)

    # --- Patch memory manager used by IConversationFlow.__init__ ---------------
    class _DummyMemoryManager:
        """A stub memory manager that does nothing."""

        async def maintain_memory(self, *_args: Any, **_kwargs: Any) -> str:
            """Perform a no-op memory maintenance and return 'ok'."""
            return "ok"

    # Ensure the import in base __init__ resolves to this stub
    monkeypatch.setattr(
        "ingenious.services.memory_manager.get_memory_manager",
        lambda _cfg, _path: _DummyMemoryManager(),
        raising=True,
    )

    # --- Controls for the stream and client lifecycle --------------------------
    controls = SimpleNamespace(
        stream_items=[],
        assistant_instances=[],
        client_close_should_raise=False,
        client_closed=False,
    )

    # --- Mock AOAI client factory ---------------------------------------------
    class _MockAsyncClient:
        """A mock async client for simulating client lifecycle."""

        async def close(self) -> None:
            """Simulate closing the client, optionally raising an error."""
            controls.client_closed = True
            if controls.client_close_should_raise:
                raise RuntimeError("close failure (simulated)")

    def _mk_client(_cfg: Any) -> _MockAsyncClient:
        """Factory function to create a mock client instance."""
        return _MockAsyncClient()

    # The flow now uses AzureClientFactory.create_openai_chat_completion_client(...)
    # Expose that method via a SimpleNamespace so the call site resolves.
    monkeypatch.setattr(
        kba,
        "AzureClientFactory",
        SimpleNamespace(create_openai_chat_completion_client=MagicMock(side_effect=_mk_client)),
    )

    # --- Mock AssistantAgent.run_stream ---------------------------------------
    class _DummyAssistant:
        """A mock AssistantAgent to control the streaming behavior."""

        def __init__(
            self,
            name: str,
            system_message: str,
            model_client: Any,
            tools: list[Any],
            reflect_on_tool_use: bool,
        ) -> None:
            """Initialize the dummy agent and record its instance for inspection."""
            self.name = name
            self.system_message = system_message
            self.model_client = model_client
            self.tools = tools
            self.reflect_on_tool_use = reflect_on_tool_use
            controls.assistant_instances.append(self)

        async def on_messages(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
            """Return a dummy response for non-streaming calls."""
            # Not used in these streaming tests
            return SimpleNamespace(chat_message=SimpleNamespace(content=""))

        def run_stream(self, task: Any, cancellation_token: Any) -> AsyncGenerator[Any, None]:
            """Yield a sequence of items defined by the test controls."""

            async def _gen() -> AsyncGenerator[Any, None]:
                """The async generator that yields test-controlled items."""
                for item in list(controls.stream_items):
                    if isinstance(item, Exception):
                        raise item
                    yield item

            return _gen()

    monkeypatch.setattr(kba, "AssistantAgent", _DummyAssistant)

    # --- Build the flow (pass the required parent service) ---------------------
    flow = kba.ConversationFlow(parent_multi_agent_chat_service=parent)

    # Avoid optional telemetry complexity; make it a no-op.
    monkeypatch.setattr(
        kba.ConversationFlow,
        "_maybe_attach_llm_usage_logger",
        lambda self, base_logger, event_type: None,
        raising=True,
    )

    # Deterministic internal behavior for the streaming path
    monkeypatch.setattr(flow, "_build_memory_context", AsyncMock(return_value=""))
    monkeypatch.setattr(flow, "_should_use_azure_search", MagicMock(return_value=False))
    monkeypatch.setattr(flow, "_get_top_k", MagicMock(return_value=3))
    # By default, disable token counting so individual tests can enable when needed
    monkeypatch.setattr(
        flow,
        "_safe_count_tokens",
        AsyncMock(side_effect=RuntimeError("counter disabled (baseline)")),
    )

    return flow, controls


# -------------------------
# Utility to drain the async stream into a list
# -------------------------
async def _collect_chunks(stream_aiter: AsyncGenerator[Any, None]) -> list[Any]:
    """Consume an async generator and return its items as a list."""
    return [c async for c in stream_aiter]


# ======================================================================
#                                 TESTS
# ======================================================================
class TestGetStreamingConversationResponse:
    """Tests for the get_streaming_conversation_response method."""

    @pytest.mark.asyncio
    async def test_happy_path_yields_expected_sequence_and_final_summary(
        self,
        flow_fixture: tuple[kba.ConversationFlow, SimpleNamespace],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Validate the standard streaming flow from start to finish.

        This test ensures that a typical sequence of events (text content followed
        by usage stats) from the agent stream is correctly transformed into a
        sequence of response chunks:
        - Initial 'Searching...' and 'Generating...' status chunks.
        - 'content' chunks for each piece of text.
        - 'token_count' chunks derived from the usage data.
        - A final 'final' chunk summarizing the interaction.
        """
        flow, controls = flow_fixture

        # Arrange stream: content → content → usage
        controls.stream_items = [
            msg_text("Hello "),
            msg_text("world."),
            msg_usage(123, 23),
        ]

        # Request with thread_id
        req = SimpleNamespace(thread_id="thread-1", user_prompt="How does it work?")

        # Act
        chunks: list[Any] = await _collect_chunks(flow.get_streaming_conversation_response(req))

        # Assert sequence and types
        assert len(chunks) >= 6  # status, status, content, content, token_count, token_count, final
        assert chunks[0].chunk_type == "status" and "Searching" in chunks[0].content
        assert chunks[1].chunk_type == "status" and "Generating" in chunks[1].content
        assert chunks[2].chunk_type == "content" and chunks[2].content == "Hello "
        assert chunks[3].chunk_type == "content" and chunks[3].content == "world."

        # There should be a token_count from usage and another just before finalization
        token_chunks = [c for c in chunks if c.chunk_type == "token_count"]
        assert [tc.token_count for tc in token_chunks] == [123, 123]

        # Final chunk checks
        final: Any = chunks[-1]
        assert final.chunk_type == "final"
        assert final.token_count == 123
        assert final.max_token_count == 23
        assert final.memory_summary == "Hello world."
        assert final.is_final is True

        # thread_id + message_id must be consistent across all chunks
        tids: set[str] = {c.thread_id for c in chunks}
        mids: set[str] = {c.message_id for c in chunks}
        assert tids == {"thread-1"}
        assert len(mids) == 1

        # Model client should have been closed
        assert controls.client_closed is True

    @pytest.mark.asyncio
    async def test_tool_event_emits_status_and_filters_tool_content(
        self,
        flow_fixture: tuple[kba.ConversationFlow, SimpleNamespace],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Ensure tool events from the agent stream are handled correctly.

        This test verifies that when a tool event object is yielded by the agent:
        - It triggers a 'Searching knowledge base...' status update.
        - It does NOT produce a 'content' chunk.
        - Subsequent normal text content is still forwarded as expected.
        """
        flow, controls = flow_fixture
        controls.stream_items = [
            ToolCallDelta(),  # detected as tool event
            msg_text("Final answer."),  # forwarded content
        ]

        # Fallback token calc
        monkeypatch.setattr(flow, "_safe_count_tokens", AsyncMock(return_value=(40, 10)))

        req = SimpleNamespace(thread_id="tid-tools", user_prompt="Q?")
        chunks: list[Any] = await _collect_chunks(flow.get_streaming_conversation_response(req))

        # Expect 3 status entries: initial searching, generating, tool event status
        status_chunks = [c for c in chunks if c.chunk_type == "status"]
        assert any("Searching knowledge base" in s.content for s in status_chunks)
        assert any("Generating" in s.content for s in status_chunks)
        assert len(status_chunks) >= 3  # the tool event adds at least one

        # The first actual content chunk should be 'Final answer.'
        content_chunks = [c for c in chunks if c.chunk_type == "content"]
        assert len(content_chunks) == 1
        assert content_chunks[0].content == "Final answer."

        # Final token count comes from fallback
        final: Any = chunks[-1]
        assert final.chunk_type == "final"
        assert final.token_count == 40
        assert final.max_token_count == 10

    @pytest.mark.asyncio
    async def test_tool_chatter_in_plain_text_is_filtered_out(
        self,
        flow_fixture: tuple[kba.ConversationFlow, SimpleNamespace],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Drop 'tool chatter' that appears as plain text in the stream.

        Some models may emit text that looks like JSON or narration about tool
        calls. This test ensures such text is identified and filtered out,
        preventing it from appearing in the user-facing 'content' chunks.
        """
        flow, controls = flow_fixture
        controls.stream_items = [
            msg_text('{"tool_calls":[{"name":"search_tool","args":{}}]}'),
            msg_text("Actual human-friendly answer."),
        ]
        monkeypatch.setattr(flow, "_safe_count_tokens", AsyncMock(return_value=(20, 5)))

        req = SimpleNamespace(thread_id="tid-plain", user_prompt="Q?")
        chunks: list[Any] = await _collect_chunks(flow.get_streaming_conversation_response(req))

        content_chunks = [c for c in chunks if c.chunk_type == "content"]
        assert len(content_chunks) == 1
        assert content_chunks[0].content == "Actual human-friendly answer."
        assert chunks[-1].token_count == 20
        assert chunks[-1].max_token_count == 5

    @pytest.mark.asyncio
    async def test_final_taskresult_flushes_missing_tail(
        self,
        flow_fixture: tuple[kba.ConversationFlow, SimpleNamespace],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Ensure content from a final TaskResult object is flushed to the stream.

        If the agent stream terminates with a special `TaskResult` object that
        contains final text not previously yielded, this test verifies that
        this "tail" content is extracted and yielded as a final 'content' chunk
        before the stream closes.
        """
        flow, controls = flow_fixture
        controls.stream_items = [
            msg_text("partial "),
            TaskResultMock("tail"),
        ]
        monkeypatch.setattr(flow, "_safe_count_tokens", AsyncMock(return_value=(10, 2)))

        req = SimpleNamespace(thread_id="tid-flush", user_prompt="Q?")
        chunks: list[Any] = await _collect_chunks(flow.get_streaming_conversation_response(req))

        contents: list[str] = [c.content for c in chunks if c.chunk_type == "content"]
        assert contents == ["partial ", "tail"]
        assert chunks[-1].chunk_type == "final"
        assert chunks[-1].token_count == 10
        assert chunks[-1].max_token_count == 2

    @pytest.mark.asyncio
    async def test_inner_exception_during_streaming_yields_error_content_and_finalizes(
        self,
        flow_fixture: tuple[kba.ConversationFlow, SimpleNamespace],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify graceful handling of exceptions raised mid-stream.

        This test simulates an exception being raised from the agent's stream
        after some content has already been yielded. It ensures that:
        - An error message is yielded as a 'content' chunk.
        - The stream is still finalized correctly with a 'final' chunk.
        - Token counting and resource cleanup still occur.
        """
        flow, controls = flow_fixture
        controls.stream_items = [
            msg_text("start "),
            Exception("boom"),
        ]
        monkeypatch.setattr(flow, "_safe_count_tokens", AsyncMock(return_value=(60, 6)))

        req = SimpleNamespace(thread_id="tid-inner", user_prompt="Q?")
        chunks: list[Any] = await _collect_chunks(flow.get_streaming_conversation_response(req))

        # Should have a content chunk echoing the error
        err_chunks = [
            c for c in chunks if c.chunk_type == "content" and "Error during streaming" in c.content
        ]
        assert len(err_chunks) == 1
        assert "boom" in err_chunks[0].content

        # Finalization present
        final: Any = chunks[-1]
        assert final.chunk_type == "final"
        assert final.token_count == 60
        assert final.max_token_count == 6
        # Memory summary includes both the start and the error text
        assert "start " in final.memory_summary
        assert "Error during streaming" in final.memory_summary

    @pytest.mark.asyncio
    async def test_outer_exception_before_streaming_yields_terminal_error_after_initial_status(
        self,
        flow_fixture: tuple[kba.ConversationFlow, SimpleNamespace],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify handling of exceptions raised during the setup phase.

        This test simulates a failure that occurs before the main streaming loop begins
        (e.g., in `_build_memory_context`). It ensures the stream yields an initial
        status update and then immediately terminates with a single 'error' chunk
        marked as final.
        """
        flow, controls = flow_fixture
        monkeypatch.setattr(
            flow,
            "_build_memory_context",
            AsyncMock(side_effect=RuntimeError("mem fail")),
        )

        req = SimpleNamespace(thread_id="tid-outer", user_prompt="Q?")
        chunks: list[Any] = await _collect_chunks(flow.get_streaming_conversation_response(req))

        assert len(chunks) == 2
        assert chunks[0].chunk_type == "status"
        assert chunks[1].chunk_type == "error"
        assert chunks[1].is_final is True
        assert "mem fail" in (chunks[1].content or "")

    @pytest.mark.asyncio
    async def test_client_cleanup_failure_does_not_affect_yielded_chunks(
        self,
        flow_fixture: tuple[kba.ConversationFlow, SimpleNamespace],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify that a failure during client cleanup is swallowed gracefully.

        This test ensures that if the underlying model client's `close()` method
        raises an exception, it is caught and logged without disrupting the
        output stream. The 'final' chunk should still be yielded correctly.
        """
        flow, controls = flow_fixture
        controls.client_close_should_raise = True
        controls.stream_items = [msg_text("ok")]
        monkeypatch.setattr(flow, "_safe_count_tokens", AsyncMock(return_value=(8, 2)))

        req = SimpleNamespace(thread_id="tid-cleanup", user_prompt="Q?")
        chunks: list[Any] = await _collect_chunks(flow.get_streaming_conversation_response(req))

        assert chunks[-1].chunk_type == "final"
        # We still expect token accounting and graceful termination.
        assert chunks[-1].token_count == 8
        assert chunks[-1].max_token_count == 2

    @pytest.mark.asyncio
    async def test_tokens_from_stream_usage_emits_token_count(
        self, flow_fixture: tuple[kba.ConversationFlow, SimpleNamespace]
    ) -> None:
        """Verify token counts are emitted when usage data is in the stream.

        This test confirms that if the agent stream provides an object with
        token usage information, a 'token_count' chunk is immediately yielded,
        and these values are carried through to the 'final' chunk.
        """
        flow, controls = flow_fixture
        controls.stream_items = [msg_usage(120, 20)]

        req = SimpleNamespace(thread_id="tid-usage", user_prompt="Q?")
        chunks: list[Any] = await _collect_chunks(flow.get_streaming_conversation_response(req))

        token_chunks = [c for c in chunks if c.chunk_type == "token_count"]
        assert [t.token_count for t in token_chunks] == [120, 120]

        final: Any = chunks[-1]
        assert final.chunk_type == "final"
        assert final.token_count == 120
        assert final.max_token_count == 20
        # No content produced in this scenario
        assert all(c.chunk_type != "content" for c in chunks[2:-2])  # after 2 initial statuses

    @pytest.mark.asyncio
    async def test_first_fallback_calls_safe_count_tokens_when_no_usage(
        self,
        flow_fixture: tuple[kba.ConversationFlow, SimpleNamespace],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Validate the first token counting fallback mechanism.

        When the agent stream does not provide token usage data, the method should
        fall back to calling `_safe_count_tokens` with the complete conversation
        context (system, user, and assistant messages) to estimate the token count.
        This test verifies that the call is made with the correct arguments and
        its result is used in the final chunk.
        """
        flow, controls = flow_fixture
        controls.stream_items = [msg_text("foo")]

        mock_counter = AsyncMock(return_value=(77, 11))
        monkeypatch.setattr(flow, "_safe_count_tokens", mock_counter)

        req = SimpleNamespace(thread_id="tid-fallback1", user_prompt="Where?")
        chunks: list[Any] = await _collect_chunks(flow.get_streaming_conversation_response(req))

        # Final carries fallback values
        assert chunks[-1].chunk_type == "final"
        assert chunks[-1].token_count == 77
        assert chunks[-1].max_token_count == 11

        # Verify _safe_count_tokens call args
        assert mock_counter.await_count == 1
        kwargs: dict[str, Any] = mock_counter.await_args.kwargs
        # system_message is produced by _streaming_system_message('')
        expected_system = flow._streaming_system_message("")
        expected_user = f"User query: {req.user_prompt}"
        expected_assistant = "foo"
        assert kwargs["system_message"] == expected_system
        assert kwargs["user_message"] == expected_user
        assert kwargs["assistant_message"] == expected_assistant
        assert kwargs["model"] == flow._config.models[0].model

    @pytest.mark.asyncio
    async def test_second_fallback_heuristic_when_safe_count_tokens_raises(
        self,
        flow_fixture: tuple[kba.ConversationFlow, SimpleNamespace],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Validate the second, heuristic-based token counting fallback.

        If both the agent stream and the `_safe_count_tokens` method fail to
        provide token counts, the system should fall back to a simple heuristic
        based on character lengths. This test confirms that this final fallback
        is triggered and calculates the expected values correctly.
        """
        flow, controls = flow_fixture
        # Make memory context non-empty to ensure system_message changes
        monkeypatch.setattr(flow, "_build_memory_context", AsyncMock(return_value="CTX "))
        # Ensure safe counter raises to force heuristic
        monkeypatch.setattr(flow, "_safe_count_tokens", AsyncMock(side_effect=RuntimeError("boom")))

        content = "ABCDEFGHIJKL"  # 12 chars
        controls.stream_items = [msg_text(content)]

        req = SimpleNamespace(thread_id="tid-fallback2", user_prompt="hello")
        # Compute expected heuristic values using the exact same logic
        system_message: str = flow._streaming_system_message("CTX ")
        user_msg: str = f"User query: {req.user_prompt}"
        expected_total: int = (len(system_message) + len(user_msg) + len(content)) // 4
        expected_completion: int = len(content) // 4

        chunks: list[Any] = await _collect_chunks(flow.get_streaming_conversation_response(req))

        final: Any = chunks[-1]
        assert final.chunk_type == "final"
        assert final.token_count == expected_total
        assert final.max_token_count == expected_completion

    @pytest.mark.asyncio
    async def test_thread_id_with_and_without_value(
        self,
        flow_fixture: tuple[kba.ConversationFlow, SimpleNamespace],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify correct propagation of thread_id in chunks.

        This test checks two scenarios:
        1. When a `thread_id` is provided in the request, it is present in all
           yielded chunks.
        2. When `thread_id` is missing or None, the chunks carry an empty string
           for the `thread_id` attribute.
        """
        flow, controls = flow_fixture
        controls.stream_items = [msg_text("a")]
        monkeypatch.setattr(flow, "_safe_count_tokens", AsyncMock(return_value=(4, 1)))

        # With thread_id
        req1 = SimpleNamespace(thread_id="T1", user_prompt="Q")
        chunks1: list[Any] = await _collect_chunks(flow.get_streaming_conversation_response(req1))
        assert {c.thread_id for c in chunks1} == {"T1"}

        # Without thread_id
        req2 = SimpleNamespace(thread_id=None, user_prompt="Q")
        controls.stream_items = [msg_text("b")]  # reset small stream for second call
        chunks2: list[Any] = await _collect_chunks(flow.get_streaming_conversation_response(req2))
        assert {c.thread_id for c in chunks2} == {""}

    @pytest.mark.asyncio
    async def test_memory_context_included_in_system_prompt_when_non_empty(
        self, flow_fixture: tuple[kba.ConversationFlow, SimpleNamespace]
    ) -> None:
        """Ensure non-empty memory context is added to the system prompt.

        This test verifies that if the `_build_memory_context` helper returns
        a non-empty string, that string is incorporated into the system message
        passed to the `AssistantAgent` during its construction.
        """
        flow, controls = flow_fixture
        # Inject a non-empty memory context
        awaitable = AsyncMock(return_value="MemoryCTX123\n")
        # Patch directly on the instance to keep scope local
        setattr(flow, "_build_memory_context", awaitable)

        controls.stream_items = [msg_text("answer")]
        req = SimpleNamespace(thread_id="tid-mem", user_prompt="Q?")
        await _collect_chunks(flow.get_streaming_conversation_response(req))

        # One assistant instance created; its system_message must contain our memory context
        assert controls.assistant_instances, "AssistantAgent was not constructed"
        sysmsg: str = controls.assistant_instances[0].system_message
        assert "MemoryCTX123" in sysmsg

    @pytest.mark.asyncio
    async def test_memory_context_absent_not_included_in_system_prompt(
        self, flow_fixture: tuple[kba.ConversationFlow, SimpleNamespace]
    ) -> None:
        """Ensure an empty memory context does not alter the system prompt.

        This test confirms that if `_build_memory_context` returns an empty
        string (the default in the fixture), the system message passed to the
        `AssistantAgent` does not contain unnecessary placeholders or extra text
        related to memory context.
        """
        flow, controls = flow_fixture

        # Baseline fixture already returns '' for memory context
        controls.stream_items = [msg_text("answer")]
        req = SimpleNamespace(thread_id="tid-mem-empty", user_prompt="Q?")
        await _collect_chunks(flow.get_streaming_conversation_response(req))

        assert controls.assistant_instances, "AssistantAgent was not constructed"
        sysmsg: str = controls.assistant_instances[0].system_message
        # Just sanity: the injected string we would have used is not present
        assert "MemoryCTX123" not in sysmsg

    @pytest.mark.asyncio
    async def test_memory_summary_truncates_when_content_exceeds_200_chars(
        self,
        flow_fixture: tuple[kba.ConversationFlow, SimpleNamespace],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify that the memory_summary in the final chunk is truncated.

        If the total accumulated content from the stream is longer than 200
        characters, the `memory_summary` attribute on the 'final' chunk should
        be truncated to 200 characters followed by an ellipsis ('...').
        """
        flow, controls = flow_fixture
        long_text = "X" * 210
        controls.stream_items = [msg_text(long_text)]
        monkeypatch.setattr(flow, "_safe_count_tokens", AsyncMock(return_value=(12, 3)))

        req = SimpleNamespace(thread_id="tid-long", user_prompt="Q?")
        chunks: list[Any] = await _collect_chunks(flow.get_streaming_conversation_response(req))

        final: Any = chunks[-1]
        assert final.chunk_type == "final"
        assert len(final.memory_summary) == 203  # 200 + '...'
        assert final.memory_summary.endswith("...")
        assert final.memory_summary.startswith("X" * 200)
