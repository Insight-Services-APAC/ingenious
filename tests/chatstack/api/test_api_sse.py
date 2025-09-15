"""SSE endpoint tests (pinpoint DI overrides via chat module + charset‑tolerant)."""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from typing import Iterator

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


@contextmanager
def _override_route_di(async_client: httpx.AsyncClient, service: FakeChatService, username: str = "tester") -> Iterator[None]:
    """Override the route's imported DI callables directly."""
    app_ref = async_client._transport.app  # type: ignore[attr-defined]
    assert isinstance(app_ref, FastAPI)

    import ingenious.api.routes.chat as chat_mod

    prev_svc = app_ref.dependency_overrides.get(chat_mod.get_chat_service)
    prev_user = app_ref.dependency_overrides.get(chat_mod.get_conditional_security)

    app_ref.dependency_overrides[chat_mod.get_chat_service] = lambda: service
    app_ref.dependency_overrides[chat_mod.get_conditional_security] = lambda: username

    # Silence namespace scanning
    orig_print_ns = chat_mod.ns_utils.print_namespace_modules
    chat_mod.ns_utils.print_namespace_modules = lambda *a, **k: None

    try:
        yield
    finally:
        if prev_svc is None:
            app_ref.dependency_overrides.pop(chat_mod.get_chat_service, None)
        else:
            app_ref.dependency_overrides[chat_mod.get_chat_service] = prev_svc

        if prev_user is None:
            app_ref.dependency_overrides.pop(chat_mod.get_conditional_security, None)
        else:
            app_ref.dependency_overrides[chat_mod.get_conditional_security] = prev_user

        chat_mod.ns_utils.print_namespace_modules = orig_print_ns


@pytest.mark.asyncio
async def test_sse_happy_path_headers_frames_and_done(async_client: httpx.AsyncClient) -> None:
    payload = {"user_prompt": "hello", "conversation_flow": "classification_agent", "user_id": "u1"}
    with _override_route_di(async_client, FakeChatService()):
        async with async_client.stream("POST", STREAM_ENDPOINT, json=payload) as resp:
            assert resp.status_code == 200
            # Starlette adds charset for str streams
            assert resp.headers["Content-Type"].startswith("text/event-stream")
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
async def test_sse_validation_error_yields_error_then_done(async_client: httpx.AsyncClient) -> None:
    payload = {"user_prompt": "x", "conversation_flow": None, "user_id": "u1"}
    with _override_route_di(async_client, FakeChatService()):
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
        (lambda: ContentFilterError(), "content filter"),
        (lambda: TokenLimitExceededError(), "token limit"),
        (lambda: Exception("generic"), "generic"),
    ],
)
async def test_sse_exception_mapping(async_client: httpx.AsyncClient, exc_factory, expected_substr: str) -> None:
    """We allow some 'data' frames before the error; we assert the next non-data event is 'error'."""
    svc = FakeChatService(exception=exc_factory())
    payload = {"user_prompt": "x", "conversation_flow": "anything", "user_id": "u1"}

    with _override_route_di(async_client, svc):
        async with async_client.stream("POST", STREAM_ENDPOINT, json=payload) as resp:
            assert resp.status_code == 200
            body = b""
            async for chunk in resp.aiter_bytes():
                body += chunk

    events = iter_sse_json(parse_sse_lines(body))
    first_non_data = next((e for e in events if e.get("event") != "data"), {})
    assert first_non_data.get("event") == "error"
    assert expected_substr.lower() in json.dumps(first_non_data).lower()
    assert events[-1] == {"event": "done"}


@pytest.mark.asyncio
async def test_sse_backfills_missing_ids(async_client: httpx.AsyncClient) -> None:
    payload = {
        "user_prompt": "hello",
        "conversation_flow": "classification_agent",
        "user_id": "u1",
        "thread_id": str(uuid.uuid4()),
    }
    with _override_route_di(async_client, FakeChatService()):
        async with async_client.stream("POST", STREAM_ENDPOINT, json=payload) as resp:
            body = b""
            async for chunk in resp.aiter_bytes():
                body += chunk

    data_events = [e for e in iter_sse_json(parse_sse_lines(body)) if e.get("event") == "data"]
    assert data_events and all(
        e["data"].get("thread_id") and e["data"].get("message_id") for e in data_events
    )
