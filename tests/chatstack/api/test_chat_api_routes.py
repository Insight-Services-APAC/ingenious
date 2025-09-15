# tests/chatstack/api/test_chat_api_routes.py
"""
Tests for ingenious/api/routes/chat.py.

Intent: Validate happy paths, error mapping, backfilling, and SSE envelopes.
Key fixtures: app (tiny FastAPI with router), client (with spy overrides).
"""

from __future__ import annotations

import json
import uuid
from typing import Any, AsyncIterator, Iterator, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ⬇️ import the SAME router and the SAME DI callables your chat.py uses
# If your file lives elsewhere, adjust the import path accordingly
from ingenious.api.routes.chat import router as chat_router
from ingenious.services.fastapi_dependencies import (
    get_chat_service as _get_chat_service,
    get_conditional_security as _get_conditional_security,
)

from ingenious.models.chat import ChatRequest, ChatResponse


# ------------------------------ Test doubles ------------------------------ #

class _SpyChatService:
    """Captures the last ChatRequest and returns deterministic responses."""

    def __init__(
        self,
        *,
        stream_exc: BaseException | None = None,
        nonstream_exc: BaseException | None = None,
        stream_chunks: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        self.last_request: ChatRequest | None = None
        self.stream_exc = stream_exc
        self.nonstream_exc = nonstream_exc
        self.stream_chunks = stream_chunks

    async def get_chat_response(self, chat_request: ChatRequest) -> ChatResponse:
        """Return a deterministic non-streaming response."""
        self.last_request = chat_request
        if self.nonstream_exc:
            raise self.nonstream_exc
        return ChatResponse(
            thread_id=chat_request.thread_id or "t1",
            message_id="m1",
            agent_response="OK",
            token_count=0,
            max_token_count=0,
            memory_summary=None,
        )

    async def get_streaming_chat_response(
        self, chat_request: ChatRequest
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield deterministic chunks for streaming tests."""
        self.last_request = chat_request
        if self.stream_exc:
            raise self.stream_exc

        # Default: one content chunk and a final chunk (matches your real behavior)
        chunks = self.stream_chunks or [
            {
                # intentionally omit keys → server should backfill
                "chunk_type": "content",
                "content": "hello",
                "is_final": False,
            },
            {
                "chunk_type": "final",
                "token_count": 0,
                "max_token_count": 0,
                "is_final": True,
            },
        ]
        for ch in chunks:
            yield ch


# ------------------------------ Test fixtures ----------------------------- #

@pytest.fixture(scope="function")
def app() -> FastAPI:
    """Build a tiny app that mounts ONLY the chat router with the standard prefix."""
    app = FastAPI()
    app.include_router(chat_router, prefix="/api/v1")
    return app


@pytest.fixture(scope="function")
def client(app: FastAPI) -> Iterator[TestClient]:
    """Provide a TestClient with overrides for DI dependencies."""
    # By default, use a spy that succeeds
    spy = _SpyChatService()

    # Return a fixed username to avoid dealing with auth in tests
    def _username() -> str:
        return "test-user"

    app.dependency_overrides[_get_chat_service] = lambda: spy
    app.dependency_overrides[_get_conditional_security] = _username

    with TestClient(app) as c:
        # Expose the spy on the client for assertions
        setattr(c, "spy_service", spy)
        yield c

    app.dependency_overrides.clear()


# ------------------------------ Test helpers ------------------------------ #

def _collect_sse_frames(resp: Any) -> list[dict[str, Any]]:
    """
    Collect only 'data: ' lines and decode them as JSON.
    Each item is the outer SSE envelope, e.g. {"event":"data"|"error"|"done", ...}
    """
    frames: list[dict[str, Any]] = []
    for ln in resp.iter_lines():
        if isinstance(ln, bytes):
            ln = ln.decode()
        if not ln or not ln.startswith("data: "):
            continue
        frames.append(json.loads(ln[6:]))
    return frames


# ---------------------------------- Tests --------------------------------- #

def test_nonstream_happy_path(client: TestClient) -> None:
    r = client.post(
        "/api/v1/chat",
        json={
            "conversation_flow": "classification-agent",
            "user_prompt": "hello",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["agent_response"] == "OK"


def test_nonstream_backfills_default_user_id(client: TestClient) -> None:
    # No user_id provided → route should backfill "unspecified_user"
    r = client.post(
        "/api/v1/chat",
        json={"conversation_flow": "classification-agent", "user_prompt": "x"},
    )
    assert r.status_code == 200
    # The spy captured the ChatRequest that reached the service
    assert getattr(client, "spy_service").last_request is not None
    assert getattr(client, "spy_service").last_request.user_id == "unspecified_user"


@pytest.mark.parametrize(
    "body, status",
    [
        ({"conversation_flow": "", "user_prompt": "x"}, 400),  # validation error
    ],
)
def test_nonstream_validation_error_maps_to_400(client: TestClient, body: dict[str, Any], status: int) -> None:
    r = client.post("/api/v1/chat", json=body)
    assert r.status_code == status


def test_nonstream_exception_mapping(client: TestClient) -> None:
    # Rebind ONLY the service override (keep username override intact)
    from ingenious.errors.content_filter_error import ContentFilterError
    from ingenious.errors.token_limit_exceeded_error import TokenLimitExceededError

    # 406
    client.app.dependency_overrides[_get_chat_service] = (
        lambda: _SpyChatService(nonstream_exc=ContentFilterError())
    )
    r = client.post("/api/v1/chat", json={"conversation_flow": "x", "user_prompt": "x"})
    assert r.status_code == 406

    # 413
    client.app.dependency_overrides[_get_chat_service] = (
        lambda: _SpyChatService(nonstream_exc=TokenLimitExceededError())
    )
    r = client.post("/api/v1/chat", json={"conversation_flow": "x", "user_prompt": "x"})
    assert r.status_code == 413

    # 500
    client.app.dependency_overrides[_get_chat_service] = (
        lambda: _SpyChatService(nonstream_exc=RuntimeError("boom"))
    )
    r = client.post("/api/v1/chat", json={"conversation_flow": "x", "user_prompt": "x"})
    assert r.status_code == 500


def test_stream_happy_path_headers_frames_and_done(client: TestClient) -> None:
    with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"conversation_flow": "classification-agent", "user_prompt": "stream me"},
    ) as r:
        # Starlette may add a charset; keep it permissive
        assert r.headers["content-type"].startswith("text/event-stream")
        frames = _collect_sse_frames(r)
        assert frames, "no frames received"
        assert any(f.get("event") == "data" for f in frames), frames
        assert frames[-1].get("event") == "done", frames


def test_stream_validation_error_yields_error_then_done(client: TestClient) -> None:
    with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"conversation_flow": "", "user_prompt": "x"},
    ) as r:
        frames = _collect_sse_frames(r)
        assert frames[0]["event"] == "error", frames
        assert frames[-1]["event"] == "done", frames


def test_stream_exception_mapping(client: TestClient) -> None:
    # Cause the stream to raise → server should emit error then done
    from ingenious.errors.content_filter_error import ContentFilterError
    from ingenious.errors.token_limit_exceeded_error import TokenLimitExceededError

    for exc, contains in [
        (ContentFilterError(), "Content"),
        (TokenLimitExceededError(), "Token"),
        (RuntimeError("boom"), "boom"),
    ]:
        client.app.dependency_overrides[_get_chat_service] = (
            lambda exc=exc: _SpyChatService(stream_exc=exc)
        )
        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            json={"conversation_flow": "classification-agent", "user_prompt": "x"},
        ) as r:
            frames = _collect_sse_frames(r)
            assert frames[0]["event"] == "error", frames
            assert contains.lower() in str(frames[0].get("error", "")).lower(), frames
            assert frames[-1]["event"] == "done", frames


def test_stream_backfills_missing_ids_in_data_chunks(client: TestClient) -> None:
    # Provide chunks with no ids; server must inject thread_id/message_id
    chunks = [
        {"chunk_type": "content", "content": "hi", "is_final": False},
        {"chunk_type": "final", "token_count": 0, "max_token_count": 0, "is_final": True},
    ]
    client.app.dependency_overrides[_get_chat_service] = (
        lambda: _SpyChatService(stream_chunks=chunks)
    )

    with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"conversation_flow": "classification-agent", "user_prompt": "x"},
    ) as r:
        frames = _collect_sse_frames(r)
        datas = [f for f in frames if f.get("event") == "data"]
        assert datas, frames

        # The 'data' envelope has a nested chunk payload at key "data"
        first_payload = datas[0].get("data") or {}
        assert isinstance(first_payload, dict), datas[0]

        # Server should have filled both ids
        assert first_payload.get("thread_id"), first_payload
        assert first_payload.get("message_id"), first_payload

        # They should look like UUIDs if none were provided
        uuid.UUID(str(first_payload["thread_id"]))
        uuid.UUID(str(first_payload["message_id"]))
