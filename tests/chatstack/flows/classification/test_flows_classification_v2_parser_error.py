"""Classification v2 streaming: parser error fallback completes stream.

Why:
- When MatchDataParser fails in streaming, the flow must fall back to a safe
  payload and still emit content deltas, a usage chunk, and a final chunk.

Usage:
- Patches `MatchDataParser` to raise.
- Patches `ConversationPattern` to a stub that returns deterministic text.
"""

from __future__ import annotations

from typing import Final

import pytest
from unittest.mock import patch

from ingenious.models.chat import ChatRequest
from ingenious.services.chat_services.multi_agent.conversation_flows.\
    classification_agent.classification_agent_v2 import ConversationFlow as ClsV2


UID: Final[str] = "uid"
TID: Final[str] = "tid"
PROMPT: Final[str] = "payload that will blow the parser"


class _BoomParser:
    """Parser stub that always raises to simulate parse failure."""

    def __init__(self, *_: object, **__: object) -> None:
        """No-op init."""

    def create_detailed_summary(self) -> tuple[str, str, str, str, str]:  # never used
        """Always raise to force fallback path."""
        raise RuntimeError("boom")


class _StubPattern:
    """Minimal conversation pattern returning deterministic text."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Ignore config; store nothing."""

    def add_topic_agent(self, *_: object, **__: object) -> None:
        """No-op; agent wiring is irrelevant for this test."""

    async def get_conversation_response(self, _msg: str) -> tuple[str, str]:
        """Return stable text for chunking and a short memory summary."""
        return ("Category: undefined\nExplanation: Fallback\nResponse: OK", "mem")

    async def close(self) -> None:
        """No-op close."""


@pytest.mark.asyncio
async def test_classification_v2_stream_parser_error_falls_back_and_completes(
    patch_config_get_config: None,
) -> None:
    """Streaming still emits content→usage→final when parser fails."""
    import ingenious.services.chat_services.multi_agent.conversation_flows.\
        classification_agent.classification_agent_v2 as v2_mod

    with patch.object(v2_mod.mp, "MatchDataParser", _BoomParser), patch.object(
        v2_mod, "ConversationPattern", _StubPattern
    ):
        req = ChatRequest(
            user_prompt=PROMPT,
            conversation_flow="classification_agent_v2",
            thread_id=TID,
            user_id=UID,
        )

        saw_content = False
        saw_usage = False
        saw_final = False

        async for chunk in ClsV2.get_streaming_conversation_response(
            message="ignored", chatrequest=req
        ):
            if chunk.chunk_type == "content":
                saw_content = True
            if chunk.chunk_type == "usage":
                assert (chunk.token_count or 0) >= 0
                assert (chunk.max_token_count or 0) >= 0
                saw_usage = True
            if chunk.chunk_type == "final":
                assert chunk.is_final is True
                saw_final = True

    assert saw_content, "Expected at least one content delta"
    assert saw_usage, "Expected usage chunk"
    assert saw_final, "Expected final chunk"
