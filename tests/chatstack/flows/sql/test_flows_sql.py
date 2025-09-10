"""
sql_manipulation_agent streaming tests.

Checks status progression (preparing → generating → executing), filters narrated
tool chatter, emits usage, and finalizes with the expected event type.
"""

from __future__ import annotations

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
    """Object whose class name triggers tool-event detection."""


@pytest.mark.asyncio
async def test_sql_agent_statuses_tool_execute_filter_and_final(
    patch_autogen_stack: None,
    stub_openai_factory: None,
    patch_config_get_config: None,
    make_min_multi_config: object,
) -> None:
    """Assert statuses, execution status on tool, filtered chatter, usage, final.

    Why:
        Tool events should surface an execution status and narrated tool JSON
        should be filtered from content deltas.
    """
    from autogen_agentchat.agents import AssistantAgent

    AssistantAgent.configure_stream(
        [
            _Msg(content="Starting..."),
            _ToolEvent(),
            _Msg(content='{"function_call": "execute_sql_tool("}'),  # filtered
            _Msg(content="Result rows: 1"),
            _Msg(usage=_Usage(33, 11)),
        ]
    )

    from ingenious.services.chat_services.multi_agent.service import (
        multi_agent_chat_service,
    )

    cfg = make_min_multi_config  # type: ignore[assignment]
    cfg = cfg()
    svc = multi_agent_chat_service(cfg, _FakeRepo(), "sql_manipulation_agent")

    req = ChatRequest(user_prompt="avg score", conversation_flow="sql_manipulation_agent", user_id="u1", thread_id="S")
    chunks = [c async for c in svc.get_streaming_chat_response(req)]

    status_texts = [c.content for c in chunks if c.chunk_type == "status"]
    assert status_texts[:2] == ["Preparing database and context...", "Generating SQL response..."]
    assert "Executing SQL query..." in status_texts

    contents = [c.content or "" for c in chunks if c.chunk_type == "content"]
    assert not any("function_call" in s for s in contents)

    assert any(c.chunk_type == "usage" for c in chunks)
    assert chunks[-1].chunk_type == "final" and chunks[-1].event_type == "sql_manipulation_streaming"
