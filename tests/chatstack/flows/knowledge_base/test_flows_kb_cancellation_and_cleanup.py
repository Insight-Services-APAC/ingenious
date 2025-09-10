"""KB streaming: cancellation handling and client cleanup.

Why:
- Ensure streaming handles cancellation by surfacing an error content chunk,
  then emitting usage and a terminal final chunk.
- Ensure the model client is closed exactly once on both success and error.

Usage:
- Relies on existing `patch_config_get_config` fixture to stub config.
- Uses unittest.mock.patch to replace AssistantAgent and client factory.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Final

import pytest
from unittest.mock import patch

import ingenious.config.config as ig_config
from ingenious.models.chat import ChatRequest
from ingenious.services.chat_services.multi_agent.conversation_flows.\
    knowledge_base_agent.knowledge_base_agent import ConversationFlow as KBFlow


FINAL_EVENT_TYPE: Final[str] = "knowledge_base_streaming"
UID: Final[str] = "uid"
TID: Final[str] = "tid"
PROMPT: Final[str] = "kb question"


class _Msg:
    """Simple streaming message with optional content."""

    def __init__(self, content: str | None = None) -> None:
        """Store message content; omits usage to exercise fallback."""
        self.content = content


class _DummyAgent:
    """Stub AssistantAgent for KB flow that can cancel or finish."""

    def __init__(self, *_: object, **__: object) -> None:
        """No-op constructor matching the real signature."""

    def run_stream(self, *args: object, **kwargs: object) -> AsyncIterator[_Msg]:
        """Yield once, then cancel or finish depending on injected mode."""
        mode: str = kwargs.pop("_mode", "ok")  # test-controlled
        async def _gen() -> AsyncIterator[_Msg]:
            yield _Msg("first part")
            if mode == "cancel":
                raise asyncio.CancelledError("simulated cancel")
            return
        return _gen()


class _SpyClient:
    """Capture close() calls across test variants."""

    def __init__(self, bucket: list[str], tag: str) -> None:
        """Track calls in `bucket` using a string tag for this client."""
        self._bucket = bucket
        self._tag = tag

    async def close(self) -> None:
        """Record close() invocation."""
        self._bucket.append(self._tag)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["ok", "cancel"])
async def test_kb_stream_cancellation_and_cleanup(
    patch_config_get_config: None,
    mode: str,
) -> None:
    """KB stream emits error→usage→final on cancel and closes client exactly once.

    Also verifies success path still emits usage and final, and always calls
    the model client's close() exactly once.
    """
    # Import the module to patch its symbols (not the class alias).
    import ingenious.services.chat_services.multi_agent.conversation_flows.\
        knowledge_base_agent.knowledge_base_agent as kb_mod

    # Spy client and factory patch.
    calls: list[str] = []
    client = _SpyClient(bucket=calls, tag="kb")

    def _factory_stub(*_: object, **__: object) -> _SpyClient:
        return client

    # Patch AssistantAgent and the client factory within the KB module.
    with patch.object(kb_mod, "AssistantAgent", _DummyAgent), patch.object(
        kb_mod.AzureClientFactory,
        "create_openai_chat_completion_client",
        side_effect=_factory_stub,
    ):
        cfg = ig_config.get_config()
        parent = type(
            "P", (), {"config": cfg, "chat_history_repository": None}
        )()  # minimal parent
        flow = KBFlow(parent_multi_agent_chat_service=parent)

        # Build a ChatRequest and drive the stream.
        req = ChatRequest(
            user_prompt=PROMPT,
            conversation_flow="knowledge_base_agent",
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
                assert chunk.event_type == FINAL_EVENT_TYPE
                saw_final = True

    # Assertions: event sequence + close() exactly once.
    if mode == "cancel":
        assert saw_error, "Expected error content chunk on cancellation"
    assert saw_usage, "Expected usage chunk (fallback permitted)"
    assert saw_final, "Expected terminal final chunk"
    assert calls == ["kb"], f"close() should be called exactly once, got {calls}"
