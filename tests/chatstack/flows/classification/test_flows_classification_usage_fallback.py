"""Classification v1 streaming: usage fallback when provider omits usage.

Why:
- When the streaming provider never reports usage, the flow must still emit a
  usage chunk via defensive token accounting, followed by a final chunk.

Usage:
- Patches AssistantAgent with a content-only streamer (no usage).
- Patches client factory to a trivial closable stub.
"""

from __future__ import annotations

from typing import AsyncIterator, Final

import pytest
from unittest.mock import patch

import ingenious.config.config as ig_config
from ingenious.models.chat import ChatRequest
from ingenious.services.chat_services.multi_agent.conversation_flows.\
    classification_agent.classification_agent import (
    ConversationFlow as ClsFlow,
    EVENT_TYPE_STREAMING,
)


UID: Final[str] = "uid"
TID: Final[str] = "tid"
PROMPT: Final[str] = "classify this message"


class _Msg:
    """Simple message with content only."""

    def __init__(self, content: str | None = None) -> None:
        """Store content delta; no usage field to trigger fallback."""
        self.content = content


class _DummyAgent:
    """Stub AssistantAgent that yields content-only deltas."""

    def __init__(self, *_: object, **__: object) -> None:
        """No-op constructor."""

    def run_stream(self, *_: object, **__: object) -> AsyncIterator[_Msg]:
        """Yield two small content chunks, never providing usage."""
        async def _gen() -> AsyncIterator[_Msg]:
            yield _Msg("Category: payload_type_1\n")
            yield _Msg("Explanation: hello\nResponse: ok")
            return
        return _gen()


class _Client:
    """Minimal closable client for the factory patch."""

    async def close(self) -> None:
        """No-op close."""


@pytest.mark.asyncio
async def test_classification_stream_usage_emitted_when_provider_omits_usage(
    patch_config_get_config: None,
) -> None:
    """Ensure a usage chunk is emitted even if the provider never reports usage."""
    import ingenious.services.chat_services.multi_agent.conversation_flows.\
        classification_agent.classification_agent as cls_mod

    with patch.object(cls_mod, "AssistantAgent", _DummyAgent), patch.object(
        cls_mod.AzureClientFactory,
        "create_openai_chat_completion_client",
        return_value=_Client(),
    ):
        cfg = ig_config.get_config()
        req = ChatRequest(
            user_prompt=PROMPT,
            conversation_flow="classification_agent",
            thread_id=TID,
            user_id=UID,
        )

        saw_usage = False
        saw_final = False

        # Call the static streaming entrypoint with `chatrequest=...`.
        async for chunk in ClsFlow.get_streaming_conversation_response(
            message="ignored", chatrequest=req
        ):
            if chunk.chunk_type == "usage":
                assert (chunk.token_count or 0) >= 0
                assert (chunk.max_token_count or 0) >= 0
                saw_usage = True
            if chunk.chunk_type == "final":
                assert chunk.is_final is True
                assert chunk.event_type == EVENT_TYPE_STREAMING
                saw_final = True

    assert saw_usage, "Expected fallback usage chunk"
    assert saw_final, "Expected terminal final chunk"
