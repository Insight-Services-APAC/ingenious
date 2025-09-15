"""Non‑streaming Chat API tests (pinpoint DI overrides via chat module).

Why this fixes your failures:
  - We override the *exact* callables that the chat routes imported:
      ingenious.api.routes.chat.get_chat_service
      ingenious.api.routes.chat.get_conditional_security
    That guarantees our fake runs and avoids env/config lookups entirely.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator, Optional

import httpx
import pytest
from fastapi import FastAPI

from ingenious.errors.content_filter_error import ContentFilterError
from ingenious.errors.token_limit_exceeded_error import TokenLimitExceededError
from ingenious.models.chat import ChatRequest, ChatResponse

DEFAULT_USER_ID = "unspecified_user"
JSON_MEDIA_TYPE_SUBSTR = "application/json"
SSE_MEDIA_TYPE = "text/event-stream"


class _FakeNonstreamService:
    """Minimal fake for the non‑streaming ChatService path."""

    def __init__(self, responder: Optional[Callable[[ChatRequest], Any]] = None) -> None:
        self._responder = responder
        self.last_request: Optional[ChatRequest] = None

    async def get_chat_response(self, chat_request: ChatRequest) -> ChatResponse:
        self.last_request = chat_request
        if self._responder is not None:
            result = self._responder(chat_request)
            if isinstance(result, Exception):
                raise result
            return result
        return ChatResponse(
            thread_id=chat_request.thread_id or "t-123",
            message_id="m-123",
            agent_response="ok",
            token_count=0,
            max_token_count=0,
            memory_summary="",
        )


@contextmanager
def _override_route_di(
    async_client: httpx.AsyncClient, chat_service: _FakeNonstreamService, username: str = "tester"
) -> Iterator[None]:
    """Override the route's imported DI callables directly."""
    app_ref = async_client._transport.app  # type: ignore[attr-defined]
    assert isinstance(app_ref, FastAPI)

    import ingenious.api.routes.chat as chat_mod

    prev_svc = app_ref.dependency_overrides.get(chat_mod.get_chat_service)
    prev_user = app_ref.dependency_overrides.get(chat_mod.get_conditional_security)

    app_ref.dependency_overrides[chat_mod.get_chat_service] = lambda: chat_service
    app_ref.dependency_overrides[chat_mod.get_conditional_security] = lambda: username

    # Silence namespace scan for deterministic tests
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


@pytest.mark.anyio
async def test_nonstream_happy_path_json_response(async_client: httpx.AsyncClient) -> None:
    """It returns 200 JSON with required ChatResponse fields from our fake."""
    fake = _FakeNonstreamService(
        responder=lambda r: ChatResponse(
            thread_id=r.thread_id or "t-abc",
            message_id="m-abc",
            agent_response="hello",
            token_count=1,
            max_token_count=1,
            memory_summary="mem",
        )
    )
    with _override_route_di(async_client, fake):
        payload = {
            "user_prompt": "hi",
            "conversation_flow": "classification_agent",
            "user_id": "u-1",
        }
        resp = await async_client.post("/api/v1/chat", json=payload)

    assert resp.status_code == 200, resp.text
    ctype = resp.headers.get("content-type", "")
    assert JSON_MEDIA_TYPE_SUBSTR in ctype
    assert SSE_MEDIA_TYPE not in ctype

    data = resp.json()
    assert data["thread_id"] == "t-abc"
    assert data["message_id"] == "m-abc"
    assert data["agent_response"] == "hello"


@pytest.mark.anyio
async def test_nonstream_default_user_id_backfill(async_client: httpx.AsyncClient) -> None:
    """Route fills missing `user_id` with DEFAULT_USER_ID before delegating."""
    fake = _FakeNonstreamService()
    with _override_route_di(async_client, fake):
        payload = {
            "user_prompt": "hi",
            "conversation_flow": "classification_agent",
            # user_id intentionally omitted
        }
        resp = await async_client.post("/api/v1/chat", json=payload)

    assert resp.status_code == 200, resp.text
    assert fake.last_request is not None
    assert fake.last_request.user_id == DEFAULT_USER_ID


@pytest.mark.anyio
async def test_nonstream_validation_error_400(async_client: httpx.AsyncClient) -> None:
    """Missing `conversation_flow` triggers HTTP 400 with value error detail."""
    fake = _FakeNonstreamService()
    with _override_route_di(async_client, fake):
        payload = {"user_prompt": "hi"}  # conversation_flow omitted
        resp = await async_client.post("/api/v1/chat", json=payload)

    assert resp.status_code == 400
    assert "conversation_flow not set" in resp.json().get("detail", "")


@pytest.mark.anyio
async def test_nonstream_error_mapping_406_and_413(async_client: httpx.AsyncClient) -> None:
    """ContentFilterError→406 and TokenLimitExceededError→413 are mapped."""
    # 406
    fake_406 = _FakeNonstreamService(responder=lambda _r: ContentFilterError("blocked"))
    with _override_route_di(async_client, fake_406):
        payload = {"user_prompt": "hi", "conversation_flow": "classification_agent"}
        resp = await async_client.post("/api/v1/chat", json=payload)
    assert resp.status_code == 406
    assert "Content filtered" in resp.json().get("detail", "")

    # 413
    fake_413 = _FakeNonstreamService(responder=lambda _r: TokenLimitExceededError("too long"))
    with _override_route_di(async_client, fake_413):
        resp = await async_client.post("/api/v1/chat", json=payload)
    assert resp.status_code == 413
    assert "Token limit exceeded" in resp.json().get("detail", "")


@pytest.mark.anyio
async def test_nonstream_unexpected_error_500(async_client: httpx.AsyncClient) -> None:
    """Unexpected exception is mapped to HTTP 500 with message (no traceback)."""
    fake_500 = _FakeNonstreamService(responder=lambda _r: RuntimeError("boom"))
    with _override_route_di(async_client, fake_500):
        payload = {"user_prompt": "hi", "conversation_flow": "classification_agent"}
        resp = await async_client.post("/api/v1/chat", json=payload)

    assert resp.status_code == 500
    body = resp.json().get("detail", "")
    assert "boom" in body
    assert "Traceback" not in body
