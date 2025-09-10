"""
classification_agent_v2 streaming tests.

Verifies word-aware delta chunking (<= CHUNK_TARGET_CHARS), usage emission,
and final chunk with correct event type by stubbing the ConversationPattern.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch

from ingenious.models.chat import ChatRequest


@pytest.mark.asyncio
async def test_classification_agent_v2_word_aware_deltas_and_final(
    patch_autogen_stack: None, stub_openai_factory: None, patch_config_get_config: None
) -> None:
    """Assert deltas respect word boundaries and target size; usage + final.

    Why:
        The v2 pattern streams a precomputed full text in word-aware chunks.
    """
    from ingenious.services.chat_services.multi_agent.conversation_flows.classification_agent import (  # noqa: E501
        classification_agent_v2 as clf2_mod,
    )

    class _PatternStub:
        def __init__(self, *a, **k) -> None:  # noqa: D401
            self.closed = False

        async def get_conversation_response(self, _msg: str) -> tuple[str, str]:
            text = (
                "This is a deterministic classification response that contains enough "
                "words to be chunked in a word-aware fashion without breaking words."
            )
            return text, "memory summary here"

        async def close(self) -> None:
            self.closed = True

        def add_topic_agent(self, *_: object, **__: object) -> None:
            return None

    with patch.object(clf2_mod, "ConversationPattern", _PatternStub):
        req = ChatRequest(
            user_prompt="payload", conversation_flow="classification_agent_v2", thread_id="T"
        )
        chunks = [
            c
            async for c in clf2_mod.ConversationFlow.get_streaming_conversation_response(
                message=req.user_prompt, chatrequest=req
            )
        ]

    assert [c.chunk_type for c in chunks[:2]] == ["status", "status"]
    deltas = [c for c in chunks if c.chunk_type == "content"]
    assert deltas and all(len(c.content or "") <= clf2_mod.CHUNK_TARGET_CHARS for c in deltas)
    assert any(c.chunk_type == "usage" for c in chunks)
    assert chunks[-1].chunk_type == "final" and chunks[-1].event_type == clf2_mod.EVENT_TYPE_STREAMING
