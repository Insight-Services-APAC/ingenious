"""
multi_agent_chat_service streaming unit tests.

Covers instance override path, legacy static streaming method, and universal
fallback (protocol v1 and v2 with correct event order and sizing).
"""

from __future__ import annotations

from typing import Any, AsyncIterator

import pytest
from unittest.mock import patch

from ingenious.models.chat import ChatRequest, ChatResponse, ChatResponseChunk

from tests.chatstack.conftest import _FakeRepo


class InstanceFlow:
    """Flow with instance override of streaming method (v1-style)."""

    def __init__(self, parent_multi_agent_chat_service: Any) -> None:
        self.parent = parent_multi_agent_chat_service

    async def get_conversation_response(self, chat_request: ChatRequest) -> ChatResponse:
        """Not used in this test."""
        return ChatResponse(
            thread_id=chat_request.thread_id or "i1",
            message_id="i2",
            agent_response="unused",
            token_count=0,
            max_token_count=0,
        )

    async def get_streaming_conversation_response(
        self, chat_request: ChatRequest
    ) -> AsyncIterator[ChatResponseChunk]:
        """Yield v1 content then final; omit IDs to test normalization."""
        yield ChatResponseChunk(
            thread_id=chat_request.thread_id or "", message_id="", chunk_type="content", content="one ", is_final=False
        )
        yield ChatResponseChunk(
            thread_id="", message_id="", chunk_type="content", content="two", is_final=False
        )
        yield ChatResponseChunk(thread_id="", message_id="", chunk_type="final", is_final=True)


class StaticFlow:
    """Flow exposing a legacy static streaming method."""

    @staticmethod
    async def get_conversation_response(chat_request: ChatRequest) -> ChatResponse:
        """Not used; present for completeness."""
        return ChatResponse(
            thread_id=chat_request.thread_id or "s1",
            message_id="s2",
            agent_response="unused",
            token_count=0,
            max_token_count=0,
        )

    @staticmethod
    async def get_streaming_conversation_response(  # type: ignore[override]
        message: str,
        topics: list[str] | None = None,
        thread_memory: str = "",
        memory_record_switch: bool = True,
        thread_chat_history: list[dict[str, str]] | None = None,
        chatrequest: ChatRequest | None = None,
    ) -> AsyncIterator[ChatResponseChunk]:
        """Yield content then final without IDs to exercise injection."""
        _ = (message, topics, thread_memory, memory_record_switch, thread_chat_history, chatrequest)
        yield ChatResponseChunk(thread_id="", message_id="", chunk_type="content", content="alpha", is_final=False)
        yield ChatResponseChunk(thread_id="", message_id="", chunk_type="final", is_final=True)


class NoStreamFlow:
    """Flow without streaming; only synchronous response available."""

    def __init__(self, parent_multi_agent_chat_service: Any) -> None:
        self.parent = parent_multi_agent_chat_service

    async def get_conversation_response(self, chat_request: ChatRequest) -> ChatResponse:
        """Return deterministic long text for fallback chunking."""
        return ChatResponse(
            thread_id=chat_request.thread_id or "n1",
            message_id="n2",
            agent_response=(" ".join(["delta"] * 60)),
            token_count=12,
            max_token_count=7,
            memory_summary="ns-mem",
        )


@pytest.fixture(name="patch_multiagent_importer")
def fixture_patch_multiagent_importer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch flow importer inside multi-agent service to return our fakes.

    Why:
        Avoid importing real flow modules for these path-selection tests.
    """

    def _fake_import(module_name: str, class_name: str) -> Any:
        if ".instance_flow." in module_name:
            return InstanceFlow
        if ".static_flow." in module_name:
            return StaticFlow
        if ".no_stream_flow." in module_name:
            return NoStreamFlow
        raise ImportError(module_name)

    monkeypatch.setattr(
        "ingenious.services.chat_services.multi_agent.service.import_class_with_fallback",
        _fake_import,
    )


@pytest.mark.asyncio
async def test_multi_agent_instance_override_v1(
    patch_multiagent_importer: None, make_min_multi_config: Any
) -> None:
    """Assert instance override path forwards v1 chunks and injects IDs.

    Why:
        The service must detect true overrides and normalize missing IDs.
    """
    from ingenious.services.chat_services.multi_agent.service import (
        multi_agent_chat_service,
    )

    cfg = make_min_multi_config(chunk_size=50)
    repo = _FakeRepo()
    svc = multi_agent_chat_service(cfg, repo, "ignored")

    req = ChatRequest(user_prompt="x", conversation_flow="instance_flow", user_id="u1", thread_id="")
    chunks = [c async for c in svc.get_streaming_chat_response(req)]

    kinds = [c.chunk_type for c in chunks]
    assert kinds[:2] == ["content", "content"]
    assert kinds[-1] == "final"
    assert all(c.thread_id for c in chunks) and all(c.message_id for c in chunks)


@pytest.mark.asyncio
async def test_multi_agent_static_legacy_streaming(
    patch_multiagent_importer: None, make_min_multi_config: Any
) -> None:
    """Assert legacy static streaming path and ID injection."""
    from ingenious.services.chat_services.multi_agent.service import (
        multi_agent_chat_service,
    )

    cfg = make_min_multi_config()
    svc = multi_agent_chat_service(cfg, _FakeRepo(), "ignored")

    req = ChatRequest(user_prompt="y", conversation_flow="static_flow", user_id="u1", thread_id="tid")
    chunks = [c async for c in svc.get_streaming_chat_response(req)]
    assert [c.chunk_type for c in chunks] == ["content", "final"]
    assert all(c.thread_id for c in chunks) and all(c.message_id for c in chunks)


@pytest.mark.asyncio
async def test_multi_agent_fallback_v1_chunking(
    patch_multiagent_importer: None, make_min_multi_config: Any
) -> None:
    """Verify v1 fallback: content chunks then final respecting chunk size."""
    from ingenious.services.chat_services.multi_agent.service import (
        multi_agent_chat_service,
    )

    cfg = make_min_multi_config(chunk_size=5, protocol=1)
    svc = multi_agent_chat_service(cfg, _FakeRepo(), "ignored")

    req = ChatRequest(user_prompt="z", conversation_flow="no_stream_flow", user_id="u1", thread_id="tid")
    chunks = [c async for c in svc.get_streaming_chat_response(req)]
    kinds = [c.chunk_type for c in chunks]
    assert kinds.count("content") > 1 and kinds[-1] == "final"
    assert all(len(c.content or "") <= 5 for c in chunks if c.chunk_type == "content")


@pytest.mark.asyncio
async def test_multi_agent_fallback_v2_protocol_target_size(
    patch_multiagent_importer: None, make_min_multi_config: Any
) -> None:
    """Verify v2 fallback sequence and target size behavior.

    Why:
        Protocol v2 must emit: status("start"), status("generation"), delta*,
        summary, usage, final. Chunk size is `max(DEFAULT_V2_TARGET_CHARS, cfg.web.streaming_chunk_size)`.
    """
    from ingenious.services.chat_services.multi_agent.service import (
        DEFAULT_V2_TARGET_CHARS,
        multi_agent_chat_service,
    )

    cfg = make_min_multi_config(chunk_size=7, protocol=2)
    svc = multi_agent_chat_service(cfg, _FakeRepo(), "ignored")
    req = ChatRequest(user_prompt="z", conversation_flow="no_stream_flow", user_id="u1", thread_id="tid")
    chunks = [c async for c in svc.get_streaming_chat_response(req)]
    kinds = [c.chunk_type for c in chunks]

    assert kinds[0:2] == ["status", "status"]
    assert "summary" in kinds and "usage" in kinds and kinds[-1] == "final"

    target = max(DEFAULT_V2_TARGET_CHARS, cfg.web.streaming_chunk_size)
    deltas = [c for c in chunks if c.chunk_type == "delta"]
    assert deltas and all(len(d.content or "") <= target for d in deltas)
