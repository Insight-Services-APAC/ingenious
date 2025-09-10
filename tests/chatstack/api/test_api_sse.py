"""
SSE endpoint integration tests.

Validates the `/api/v1/chat/stream` Server-Sent Events (SSE) contract:
headers, frame shape (`"data: {json}\\n\\n"`), error mapping, ID backfilling,
and terminal `"done"` sentinel. Uses `httpx.AsyncClient` against the ASGI app.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from ingenious.errors.content_filter_error import ContentFilterError
from ingenious.errors.token_limit_exceeded_error import TokenLimitExceededError

from tests.chatstack.conftest import (
    SSE_PREFIX,
    STREAM_ENDPOINT,
    FakeChatService,
    iter_sse_json,
    parse_sse_lines,
)


@pytest.mark.asyncio
async def test_sse_happy_path_headers_frames_and_done(
    async_client: httpx.AsyncClient,
) -> None:
    """Assert 200, required headers, frame shape, >=2 data, and terminal done.

    Why:
        The endpoint guarantees specific headers and exact `"data: {json}\\n\\n"`
        frames; clients rely on a final `"done"` event for cleanup.
    """
    payload = {
        "user_prompt": "hello",
        "conversation_flow": "classification_agent",
        "user_id": "u1",
    }
    async with async_client.stream("POST", STREAM_ENDPOINT, json=payload) as resp:
        assert resp.status_code == 200
        assert resp.headers["Content-Type"] == "text/event-stream"
        assert resp.headers["Cache-Control"] == "no-cache"
        assert resp.headers["Connection"] == "keep-alive"
        assert resp.headers["X-Accel-Buffering"] == "no"

        body = b""
        async for chunk in resp.aiter_bytes():
            body += chunk

    frames = parse_sse_lines(body)
    assert frames and all(f.startswith(SSE_PREFIX) and f.endswith("\n\n") for f in frames)
    events = iter_sse_json(frames)
    data_events = [e for e in events if e.get("event") == "data"]
    assert len(data_events) >= 2
    assert events[-1] == {"event": "done"}

    for e in data_events:
        d = e["data"]
        assert isinstance(d, dict)
        assert d.get("thread_id")
        assert d.get("message_id")


@pytest.mark.asyncio
async def test_sse_validation_error_yields_error_then_done(
    async_client: httpx.AsyncClient,
) -> None:
    """Assert empty/None `conversation_flow` yields single 'error' then 'done'.

    Why:
        The endpoint performs early validation and streams error + done instead
        of failing the HTTP request.
    """
    payload = {"user_prompt": "x", "conversation_flow": None, "user_id": "u1"}
    async with async_client.stream("POST", STREAM_ENDPOINT, json=payload) as resp:
        assert resp.status_code == 200
        body = b""
        async for chunk in resp.aiter_bytes():
            body += chunk

    kinds = [e.get("event") for e in iter_sse_json(parse_sse_lines(body))]
    assert kinds == ["error", "done"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc_factory, expected_substr",
    [
        (lambda: ValueError("boom"), "boom"),
        (lambda: ContentFilterError(), ContentFilterError.DEFAULT_MESSAGE),
        (
            lambda: TokenLimitExceededError(),
            TokenLimitExceededError.DEFAULT_MESSAGE,
        ),
        (lambda: Exception("generic"), "generic"),
    ],
)
async def test_sse_exception_mapping(
    async_client: httpx.AsyncClient,
    exc_factory: Any,
    expected_substr: str,
) -> None:
    """Ensure known exceptions map to error + done with stable messages.

    Why:
        The endpoint emits friendly default messages for known errors and always
        follows with a terminal `"done"` frame.
    """
    from ingenious.services.dependencies import get_chat_service as _dep

    app_ref = async_client._transport.app  # type: ignore[attr-defined]
    assert isinstance(app_ref, FastAPI)

    def _service_factory() -> FakeChatService:
        return FakeChatService(exception=exc_factory())

    app_ref.dependency_overrides[_dep] = _service_factory

    payload = {"user_prompt": "x", "conversation_flow": "anything", "user_id": "u1"}
    async with async_client.stream("POST", STREAM_ENDPOINT, json=payload) as resp:
        assert resp.status_code == 200
        body = b""
        async for chunk in resp.aiter_bytes():
            body += chunk

    events = iter_sse_json(parse_sse_lines(body))
    assert events[0]["event"] == "error"
    assert expected_substr.lower() in json.dumps(events[0]).lower()
    assert events[-1] == {"event": "done"}


@pytest.mark.asyncio
async def test_sse_backfills_missing_ids(async_client: httpx.AsyncClient) -> None:
    """Assert server injects IDs when chunks omit `thread_id`/`message_id`.

    Why:
        Clients rely on IDs for correlation; the endpoint enforces continuity.
    """
    payload = {
        "user_prompt": "hello",
        "conversation_flow": "classification_agent",
        "user_id": "u1",
        "thread_id": str(uuid.uuid4()),
    }
    async with async_client.stream("POST", STREAM_ENDPOINT, json=payload) as resp:
        body = b""
        async for chunk in resp.aiter_bytes():
            body += chunk

    data_events = [
        e for e in iter_sse_json(parse_sse_lines(body)) if e.get("event") == "data"
    ]
    assert data_events and all(
        e["data"].get("thread_id") and e["data"].get("message_id") for e in data_events
    )
