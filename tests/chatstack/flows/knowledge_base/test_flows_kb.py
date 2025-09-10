"""
knowledge_base_agent streaming tests.

Validates status ordering, tool-event handling (status shown but tool chatter
filtered), usage emission (or fallback), and final chunk with event type.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ingenious.models.chat import ChatRequest

from tests.chatstack.conftest import _FakeRepo


class _Usage:
    """Tiny usage holder with token counters."""

    def __init__(self, total_tokens: int, completion_tokens: int) -> None:
        self.total_tokens = total_tokens
        self.completion_tokens = completion_tokens


class _Msg:
    """Base for fake stream messages."""

    def __init__(self, content: str | None = None, usage: _Usage | None = None) -> None:
        self.content = content
        self.usage = usage


class _ToolEvent:
    """Object whose class name triggers tool-event detection in the flow."""


class _TaskResult:
    """Mimic TaskResult with `.messages[-1].content` for final flush."""

    def __init__(self, text: str) -> None:
        self.messages = [SimpleNamespace(content=text)]


@pytest.mark.asyncio
async def test_knowledge_base_agent_status_tool_filter_usage_final(
    patch_autogen_stack: None,
    stub_openai_factory: None,
    patch_config_get_config: None,
    make_min_multi_config: object,
) -> None:
    """Assert statuses, filtered tool chatter, usage, and final event type.

    Why:
        The streaming path should report tool usage as status, drop tool JSON
        chatter, and include a usage chunk before finalization.
    """
    from autogen_agentchat.agents import AssistantAgent

    AssistantAgent.configure_stream(
        [
            _ToolEvent(),
            _Msg(content="Answer "),
            _Msg(content='{"tool_calls":[{"fn":"search"}]}'),  # filtered
            _Msg(usage=_Usage(20, 7)),
            _TaskResult(text="final piece"),
        ]
    )

    from ingenious.services.chat_services.multi_agent.service import (
        multi_agent_chat_service,
    )

    cfg = make_min_multi_config  # type: ignore[assignment]
    cfg = cfg()  # call the factory to get a config object

    svc = multi_agent_chat_service(cfg, _FakeRepo(), "knowledge_base_agent")
    req = ChatRequest(user_prompt="kb?", conversation_flow="knowledge_base_agent", user_id="u1", thread_id="K")
    chunks = [c async for c in svc.get_streaming_chat_response(req)]

    status_texts = [c.content for c in chunks if c.chunk_type == "status"]
    assert status_texts[:2] == ["Searching knowledge base...", "Generating response..."]
    assert "Searching knowledge base..." in status_texts  # tool event surfaced as status

    contents = [c.content or "" for c in chunks if c.chunk_type == "content"]
    assert any("Answer " in s for s in contents)
    assert not any("tool_calls" in s for s in contents)

    assert any(c.chunk_type == "usage" for c in chunks)
    assert chunks[-1].chunk_type == "final" and chunks[-1].event_type == "knowledge_base_streaming"


@pytest.mark.asyncio
async def test_knowledge_base_agent_stream_error_emits_content_and_usage(
    patch_autogen_stack: None,
    stub_openai_factory: None,
    patch_config_get_config: None,
    make_min_multi_config: object,
) -> None:
    """If stream fails, surface a content error, still emit usage, then final.

    Why:
        Robust error handling should not terminate the stream abruptly.
    """
    from autogen_agentchat.agents import AssistantAgent

    AssistantAgent.configure_stream([_Msg(content="prefix")], raise_at_index=0)

    from ingenious.services.chat_services.multi_agent.service import (
        multi_agent_chat_service,
    )

    cfg = make_min_multi_config  # type: ignore[assignment]
    cfg = cfg()
    svc = multi_agent_chat_service(cfg, _FakeRepo(), "knowledge_base_agent")
    req = ChatRequest(user_prompt="kb?", conversation_flow="knowledge_base_agent", user_id="u1", thread_id="K")
    chunks = [c async for c in svc.get_streaming_chat_response(req)]

    assert any(
        c.chunk_type == "content" and "Error during streaming" in (c.content or "")
        for c in chunks
    )
    assert any(c.chunk_type == "usage" for c in chunks)
    assert chunks[-1].chunk_type == "final"
