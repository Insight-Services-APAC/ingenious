"""ChatService: persist memory when backend emits only a final chunk.

Expects one user message saved, **no assistant message**, and one memory entry.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

import pytest

from ingenious.models.chat import ChatRequest, ChatResponseChunk
from ingenious.services.chat_service import ChatService


class _FakeBackend:
    """Backend that emits only a final chunk with a memory summary."""

    def __init__(self, *_: Any, **__: Any) -> None:
        return None

    async def get_chat_response(self, *_: Any, **__: Any) -> Any:  # pragma: no cover
        raise AssertionError("Should not be called in this test")

    async def get_streaming_chat_response(
        self, _req: ChatRequest
    ) -> AsyncIterator[ChatResponseChunk]:
        yield ChatResponseChunk(
            thread_id=None,
            message_id=None,
            chunk_type="final",
            memory_summary="ms",
            is_final=True,
        )


class _Repo:
    """Minimal in-memory repository capturing writes."""

    def __init__(self) -> None:
        self.messages: list[Any] = []
        self.memories: list[Any] = []

    async def add_message(self, msg: Any) -> str:
        self.messages.append(msg)
        return "m"

    async def add_memory(self, msg: Any) -> str:
        self.memories.append(msg)
        return "mem"

    async def get_thread_messages(self, _tid: str) -> list[Any]:
        return []


@pytest.mark.asyncio
async def test_chat_service_persists_memory_when_no_content_final_only(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only memory should be saved when no content chunks are streamed."""
    # Force importer to return our fake backend.
    monkeypatch.setattr(
        "ingenious.utils.imports.import_class_with_fallback",
        lambda *a, **k: _FakeBackend,
    )

    cfg = type("Cfg", (), {"models": [type("M", (), {})()]})()
    repo = _Repo()
    svc = ChatService(
        chat_service_type="anything",
        chat_history_repository=repo,
        conversation_flow="x",
        config=cfg,
    )
    req = ChatRequest(
        user_prompt="hi",
        conversation_flow="x",
        user_id="u",
        thread_id="t",
    )

    # Consume the stream.
    async for _ in svc.get_streaming_chat_response(req):
        pass

    # Assert repository writes.
    assert any(m.role == "user" for m in repo.messages)
    assert not any(m.role == "assistant" for m in repo.messages)
    assert len(repo.memories) == 1
