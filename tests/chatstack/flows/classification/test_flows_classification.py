"""
classification_agent streaming tests.

Asserts statuses ordering, content deltas, usage emission, error-to-content
behavior, and final chunk with the expected event type.
"""

from __future__ import annotations

import pytest

from ingenious.models.chat import ChatRequest

from tests.chatstack.conftest import _FakeRepo  # noqa: F401 - imported for consistency (not used here)

class _Usage:
    """Tiny usage holder with token counters."""

    def __init__(self, total_tokens: int, completion_tokens: int) -> None:
        self.total_tokens = total_tokens
        self.completion_tokens = completion_tokens


class _Msg:
    """Base for fake stream messages (content/usage)."""

    def __init__(self, content: str | None = None, usage: _Usage | None = None) -> None:
        self.content = content
        self.usage = usage


@pytest.mark.asyncio
async def test_classification_agent_streaming_sequence(
    patch_autogen_stack: None, stub_openai_factory: None, patch_config_get_config: None
) -> None:
    """Assert statuses → content* → usage → final with expected event type.

    Why:
        This flow emits two status messages first, then deltas, usage, and a
        final with `event_type="classification_streaming"`.
    """
    from autogen_agentchat.agents import AssistantAgent

    AssistantAgent.configure_stream(
        [_Msg(content="Hello"), _Msg(content=" world"), _Msg(usage=_Usage(12, 5))]
    )

    from ingenious.services.chat_services.multi_agent.conversation_flows.classification_agent import (  # noqa: E501
        classification_agent as clf_mod,
    )

    req = ChatRequest(user_prompt="hi", conversation_flow="classification_agent", thread_id="T")
    chunks = [
        c
        async for c in clf_mod.ConversationFlow.get_streaming_conversation_response(
            message=req.user_prompt, chatrequest=req
        )
    ]

    assert [c.content for c in chunks[:2]] == [
        clf_mod.STATUS_PREPARING,
        clf_mod.STATUS_GENERATING,
    ]
    kinds = [c.chunk_type for c in chunks]
    assert kinds.count("content") >= 2 and "usage" in kinds and kinds[-1] == "final"
    assert chunks[-1].event_type == clf_mod.EVENT_TYPE_STREAMING


@pytest.mark.asyncio
async def test_classification_agent_streaming_error_to_content(
    patch_autogen_stack: None, stub_openai_factory: None, patch_config_get_config: None
) -> None:
    """Stream raises → a content chunk with error string precedes final.

    Why:
        The flow surfaces streaming errors as content (not hard failures).
    """
    from autogen_agentchat.agents import AssistantAgent

    AssistantAgent.configure_stream([_Msg(content="A"), _Msg(content="B")], raise_at_index=1)

    from ingenious.services.chat_services.multi_agent.conversation_flows.classification_agent import (  # noqa: E501
        classification_agent as clf_mod,
    )

    req = ChatRequest(user_prompt="err", conversation_flow="classification_agent", thread_id="T")
    chunks = [
        c
        async for c in clf_mod.ConversationFlow.get_streaming_conversation_response(
            message=req.user_prompt, chatrequest=req
        )
    ]
    contents = [c.content or "" for c in chunks if c.chunk_type == "content"]
    assert any("Error during streaming" in s for s in contents)
    assert chunks[-1].chunk_type == "final"
