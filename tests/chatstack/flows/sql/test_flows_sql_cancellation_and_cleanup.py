"""SQL streaming: cancellation handling and client cleanup.

Why:
- Validate stream robustness on cancellation (error content, usage, final).
- Ensure model client is closed once on both success and error paths.

Usage:
- Uses patched AssistantAgent and Azure client factory within SQL module scope.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Final

import pytest
from unittest.mock import patch

import ingenious.config.config as ig_config
from ingenious.models.chat import ChatRequest
from ingenious.services.chat_services.multi_agent.conversation_flows.\
    sql_manipulation_agent.sql_manipulation_agent import (
    ConversationFlow as SQLFlow,
    EVENT_TYPE_STREAMING,
)

UID: Final[str] = "uid"
TID: Final[str] = "tid"
PROMPT: Final[str] = "avg score?"


class _Msg:
    """Simple streaming message wrapper for content-only deltas."""
    def __init__(self, content: str | None = None) -> None:
        self.content = content


class _DummyAgentOk:
    """Stub AssistantAgent that streams content and finishes normally."""
    def __init__(self, *_: object, **__: object) -> None:
        pass

    def run_stream(self, *args: object, **kwargs: object) -> AsyncIterator[_Msg]:
        async def _gen() -> AsyncIterator[_Msg]:
            yield _Msg("hello")
            return
        return _gen()


class _DummyAgentCancel:
    """Stub AssistantAgent that streams once and then raises CancelledError."""
    def __init__(self, *_: object, **__: object) -> None:
        pass

    def run_stream(self, *args: object, **kwargs: object) -> AsyncIterator[_Msg]:
        async def _gen() -> AsyncIterator[_Msg]:
            yield _Msg("hello")
            # Simulate a mid-stream cancellation from the model/agent.
            raise asyncio.CancelledError("stop")
        return _gen()


class _SpyClient:
    """Spy Azure client to assert close() invocations."""
    def __init__(self, bucket: list[str], tag: str) -> None:
        self._bucket = bucket
        self._tag = tag

    async def close(self) -> None:
        self._bucket.append(self._tag)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["ok", "cancel"])
async def test_sql_stream_cancellation_and_cleanup(
    patch_config_get_config: None,
    mode: str,
) -> None:
    """SQL stream emits error→usage→final on cancel and closes client once."""
    import ingenious.services.chat_services.multi_agent.conversation_flows.\
        sql_manipulation_agent.sql_manipulation_agent as sql_mod

    calls: list[str] = []
    client = _SpyClient(bucket=calls, tag="sql")

    def _factory_stub(*_: object, **__: object) -> _SpyClient:
        return client

    # Choose the appropriate stub agent for the scenario.
    agent_cls = _DummyAgentCancel if mode == "cancel" else _DummyAgentOk

    with patch.object(sql_mod, "AssistantAgent", agent_cls), patch.object(
        sql_mod.AzureClientFactory,
        "create_openai_chat_completion_client",
        side_effect=_factory_stub,
    ):
        cfg = ig_config.get_config()
        parent = type("P", (), {"config": cfg, "chat_history_repository": None})()
        flow = SQLFlow(parent_multi_agent_chat_service=parent)

        req = ChatRequest(
            user_prompt=PROMPT,
            conversation_flow="sql_manipulation_agent",
            thread_id=TID,
            user_id=UID,
        )

        saw_error = False
        saw_usage = False
        saw_final = False

        async for chunk in flow.get_streaming_conversation_response(req):
            if mode == "cancel" and chunk.chunk_type == "content":
                if chunk.content and "[Error during streaming:" in chunk.content:
                    saw_error = True
            if chunk.chunk_type == "usage":
                assert (chunk.token_count or 0) >= 0
                assert (chunk.max_token_count or 0) >= 0
                saw_usage = True
            if chunk.chunk_type == "final":
                assert chunk.is_final is True
                assert chunk.event_type == EVENT_TYPE_STREAMING
                saw_final = True

    if mode == "cancel":
        assert saw_error, "Expected error content chunk on cancellation"
    assert saw_usage, "Expected usage chunk (fallback permitted)"
    assert saw_final, "Expected terminal final chunk"
    assert calls == ["sql"], f"close() should be called exactly once, got {calls}"
