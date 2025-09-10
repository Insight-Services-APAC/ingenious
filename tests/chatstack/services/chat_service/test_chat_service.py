"""
ChatService streaming unit tests.

Covers native streaming pass-through + persistence, chunked fallback when the
backend lacks streaming, mid-stream error persistence, and no-persistence
conditions when disabled or user_id is missing.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

import pytest
from unittest.mock import patch

from ingenious.models.chat import ChatRequest, ChatResponse, ChatResponseChunk

from tests.chatstack.conftest import SAMPLE_PROMPT, _FakeRepo


class _FakeBackendBase:
    """Base fake backend mirroring constructor signature."""

    def __init__(
        self, config: Any, chat_history_repository: Any, conversation_flow: str
    ) -> None:
        self.config = config
        self.chat_history_repository = chat_history_repository
        self.conversation_flow = conversation_flow


class FakeBackendNative(_FakeBackendBase):
    """Backend with native streaming."""

    async def get_chat_response(self, chat_request: ChatRequest) -> ChatResponse:
        """Return minimal non-streaming response (unused in native path)."""
        return ChatResponse(
            thread_id=chat_request.thread_id or "tn",
            message_id="mn",
            agent_response="unused",
            token_count=0,
            max_token_count=0,
            memory_summary="mem",
        )

    async def get_streaming_chat_response(
        self, chat_request: ChatRequest
    ) -> AsyncIterator[ChatResponseChunk]:
        """Yield two content chunks, one usage, and a final with memory summary."""
        tid = chat_request.thread_id or "tn"
        mid = "mn"
        yield ChatResponseChunk(
            thread_id=tid, message_id=mid, chunk_type="content", content="hello ", is_final=False
        )
        yield ChatResponseChunk(
            thread_id=tid, message_id=mid, chunk_type="content", content="world", is_final=False
        )
        yield ChatResponseChunk(
            thread_id=tid, message_id=mid, chunk_type="usage", token_count=42, max_token_count=10, is_final=False
        )
        yield ChatResponseChunk(
            thread_id=tid, message_id=mid, chunk_type="final", memory_summary="summary", is_final=True
        )


class FakeBackendNoStream(_FakeBackendBase):
    """Backend without streaming; returns a full response."""

    async def get_chat_response(self, chat_request: ChatRequest) -> ChatResponse:
        """Return a long deterministic text for fallback chunking."""
        text = "abcdefg hijklmn opqrstu vwxyz"
        return ChatResponse(
            thread_id=chat_request.thread_id or "tf",
            message_id="mf",
            agent_response=text,
            token_count=9,
            max_token_count=5,
            memory_summary="memsum",
            event_type="evt",
        )


class FakeBackendErrorStream(_FakeBackendBase):
    """Backend that raises on the second yield to test persistence in `finally`."""

    async def get_chat_response(self, chat_request: ChatRequest) -> ChatResponse:
        """Return minimal response (unused)."""
        return ChatResponse(
            thread_id=chat_request.thread_id or "te",
            message_id="me",
            agent_response="unused",
            token_count=0,
            max_token_count=0,
        )

    async def get_streaming_chat_response(
        self, chat_request: ChatRequest
    ) -> AsyncIterator[ChatResponseChunk]:
        """Yield one content chunk then raise."""
        tid = chat_request.thread_id or "te"
        mid = "me"
        yield ChatResponseChunk(
            thread_id=tid, message_id=mid, chunk_type="content", content="only ", is_final=False
        )
        raise ValueError("boom")


@pytest.mark.asyncio
async def test_chat_service_native_streaming_persists(fake_repo: _FakeRepo) -> None:
    """Assert native streaming is forwarded and persistence runs in `finally`.

    Why:
        The facade must accumulate content and write user, assistant, and memory.
    """
    cfg = type("Cfg", (), {"web": type("Web", (), {"streaming_chunk_size": 100})})()

    with patch(
        "ingenious.utils.imports.import_class_with_fallback", return_value=FakeBackendNative
    ):
        from ingenious.services.chat_service import ChatService

        svc = ChatService(
            chat_service_type="fake",
            chat_history_repository=fake_repo,
            conversation_flow="flow",
            config=cfg,
        )

    req = ChatRequest(user_prompt=SAMPLE_PROMPT, conversation_flow="x", user_id="u1", thread_id="T")
    observed: list[ChatResponseChunk] = [c async for c in svc.get_streaming_chat_response(req)]

    kinds = [c.chunk_type for c in observed]
    assert kinds[:2] == ["content", "content"]
    assert "usage" in kinds and kinds[-1] == "final"

    assistant_msgs = [m for m in fake_repo.messages if getattr(m, "role", "") == "assistant"]
    assert assistant_msgs and assistant_msgs[-1].content.strip() == "hello world"
    assert fake_repo.memories and fake_repo.memories[-1].content == "summary"


@pytest.mark.asyncio
async def test_chat_service_fallback_chunking_and_persist(fake_repo: _FakeRepo) -> None:
    """Assert chunked fallback boundaries and single persistence at end.

    Why:
        When no native streaming exists, the facade must chunk the full text and
        emit a terminal `final`, then persist the combined text and memory.
    """
    cfg = type("Cfg", (), {"web": type("Web", (), {"streaming_chunk_size": 7})})()

    with patch(
        "ingenious.utils.imports.import_class_with_fallback", return_value=FakeBackendNoStream
    ):
        from ingenious.services.chat_service import ChatService

        svc = ChatService(
            chat_service_type="fake",
            chat_history_repository=fake_repo,
            conversation_flow="flow",
            config=cfg,
        )

    req = ChatRequest(user_prompt=SAMPLE_PROMPT, conversation_flow="x", user_id="u1", thread_id="TF")
    observed = [c async for c in svc.get_streaming_chat_response(req)]

    content_chunks = [c for c in observed if c.chunk_type == "content"]
    assert content_chunks and all(len(c.content or "") <= 7 for c in content_chunks)
    assert observed[-1].chunk_type == "final"

    roles = [getattr(m, "role", "") for m in fake_repo.messages]
    assert "user" in roles and "assistant" in roles
    assert fake_repo.memories and fake_repo.memories[-1].content == "memsum"


@pytest.mark.asyncio
async def test_chat_service_mid_stream_error_still_persists(fake_repo: _FakeRepo) -> None:
    """Ensure persistence runs on error with accumulated content.

    Why:
        The facade must not lose previously streamed content if iteration fails.
    """
    cfg = type("Cfg", (), {"web": type("Web", (), {"streaming_chunk_size": 50})})()

    with patch(
        "ingenious.utils.imports.import_class_with_fallback", return_value=FakeBackendErrorStream
    ):
        from ingenious.services.chat_service import ChatService

        svc = ChatService(
            chat_service_type="fake",
            chat_history_repository=fake_repo,
            conversation_flow="flow",
            config=cfg,
        )

    req = ChatRequest(user_prompt=SAMPLE_PROMPT, conversation_flow="x", user_id="u1", thread_id="TE")

    with pytest.raises(ValueError):
        async for _ in svc.get_streaming_chat_response(req):
            pass

    assistant_msgs = [m for m in fake_repo.messages if getattr(m, "role", "") == "assistant"]
    assert assistant_msgs and (assistant_msgs[-1].content or "").startswith("only")


@pytest.mark.asyncio
async def test_chat_service_no_persistence_when_disabled_or_no_user(
    fake_repo: _FakeRepo,
) -> None:
    """Verify persistence is skipped when disabled or user missing.

    Why:
        Guards avoid unwanted writes and tolerate anonymous callers.
    """
    cfg = type("Cfg", (), {"web": type("Web", (), {"streaming_chunk_size": 10})})()

    with patch(
        "ingenious.utils.imports.import_class_with_fallback", return_value=FakeBackendNative
    ):
        from ingenious.services.chat_service import ChatService

        # memory_record=False
        svc1 = ChatService("fake", fake_repo, "flow", cfg)
        req1 = ChatRequest(
            user_prompt=SAMPLE_PROMPT,
            conversation_flow="x",
            user_id="u1",
            thread_id="A",
            memory_record=False,
        )
        async for _ in svc1.get_streaming_chat_response(req1):
            pass

        # user_id missing
        svc2 = ChatService("fake", fake_repo, "flow", cfg)
        req2 = ChatRequest(user_prompt=SAMPLE_PROMPT, conversation_flow="x", user_id=None, thread_id="B")
        async for _ in svc2.get_streaming_chat_response(req2):
            pass

    # No new memory entries tied to "summary" at the end of this test
    assert not fake_repo.memories or all(
        getattr(m, "content", "") != "summary" for m in fake_repo.memories[-2:]
    )
