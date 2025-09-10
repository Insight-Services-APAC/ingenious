"""Multi-agent v2 fallback: usage heuristics and summary trimming.

This test forces the multi-agent service into the v2 streaming fallback path
(no native streaming) and simulates a token-counter failure to verify:
- status:start and status:generation are emitted.
- delta chunks are produced.
- summary chunk has a memory_summary trimmed to <= 200 chars.
- usage chunk is emitted with positive counts (heuristic fallback).
- final chunk closes the stream.

Why:
Covers v2 fallback heuristics and summary trimming, ensuring robust UX when
accurate token accounting is unavailable.
"""

from __future__ import annotations

from typing import Any, AsyncIterator
from unittest.mock import patch

import pytest

from ingenious.models.chat import ChatRequest, ChatResponse, ChatResponseChunk
from ingenious.services.chat_services.multi_agent.service import (
    multi_agent_chat_service,
)

LONG_TEXT_LEN: int = 900
STREAM_V2: int = 2
CHUNK_SIZE: int = 120
FLOW_NAME: str = "no_stream"
USER_PROMPT: str = "hello world"
THREAD_ID: str = "tid-1"
MESSAGE_ID: str = "mid-1"


class _Cfg:
    """Config stub for the multi-agent service."""

    class Web:
        stream_protocol_version: int = STREAM_V2
        streaming_chunk_size: int = CHUNK_SIZE

    class ChatServiceCfg:
        enable_builtin_workflows: bool = True

    web = Web()
    chat_service = ChatServiceCfg()
    openai_service_instance: object = object()


class _Repo:
    """Minimal repository that satisfies interface."""

    async def add_message(self, _msg: Any) -> str:  # pragma: no cover
        """Return a dummy id; not used for coverage of this path."""
        return "m"

    async def add_memory(self, _msg: Any) -> str:  # pragma: no cover
        """Return a dummy id; not used for coverage of this path."""
        return "mm"

    async def get_thread_messages(self, _tid: str) -> list[Any]:  # pragma: no cover
        """Return empty list; memory is not used in this scenario."""
        return []


class NoStreamFlow:
    """Flow with only non-streaming; forces v2 fallback in the service."""

    def __init__(self, parent_multi_agent_chat_service: Any) -> None:
        """Record config (unused) to mirror real flows."""
        self._cfg = parent_multi_agent_chat_service.config

    async def get_conversation_response(self, chat_request: ChatRequest) -> ChatResponse:
        """Return a long response text to exercise chunking and summary trim."""
        text = "X" * LONG_TEXT_LEN
        return ChatResponse(
            thread_id=chat_request.thread_id or THREAD_ID,
            message_id=MESSAGE_ID,
            agent_response=text,
            token_count=0,  # force service to try token counter then fallback
            max_token_count=0,
            memory_summary=text,
        )


@pytest.mark.anyio
async def test_multi_agent_v2_fallback_emits_usage_on_counter_error_and_trims_summary() -> None:
    """Ensure v2 fallback emits heuristics usage and trims memory summary."""
    svc = multi_agent_chat_service(
        config=_Cfg(), chat_history_repository=_Repo(), conversation_flow=FLOW_NAME
    )

    req = ChatRequest(
        user_prompt=USER_PROMPT, conversation_flow=FLOW_NAME, user_id="u1"
    )

    # Patch importer to return our NoStreamFlow and the token counter to raise.
    with patch(
        "ingenious.services.chat_services.multi_agent.service.import_class_with_fallback",
        return_value=NoStreamFlow,
    ), patch(
        "ingenious.utils.token_counter.num_tokens_from_messages",
        side_effect=RuntimeError("counter failed"),
    ):
        chunks: list[ChatResponseChunk] = []
        async for ch in svc.get_streaming_chat_response(req):
            chunks.append(ch)

    # status:start and status:generation present
    assert any(c.chunk_type == "status" and c.content == "start" for c in chunks)
    assert any(c.chunk_type == "status" and c.content == "generation" for c in chunks)

    # delta content present (word-aware chunking done by service)
    assert any(c.chunk_type in {"delta", "content"} for c in chunks)

    # summary present and memory_summary trimmed to <= 200
    summaries = [c for c in chunks if c.chunk_type == "summary"]
    assert summaries, "Expected a summary chunk in v2 fallback."
    ms = summaries[0].memory_summary or ""
    assert len(ms) <= 200

    # usage emitted with positive counts via heuristics
    usages = [c for c in chunks if c.chunk_type == "usage"]
    assert usages, "Expected a usage chunk even when counter fails."
    assert int(usages[0].token_count or 0) > 0
    assert int(usages[0].max_token_count or 0) > 0

    # final chunk terminates stream
    assert chunks and chunks[-1].chunk_type == "final"
