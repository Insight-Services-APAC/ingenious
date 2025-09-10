# tests/test_streaming/test_api_nonstream_chat.py
"""Non-streaming Chat API route tests.

These tests cover `POST /api/v1/chat` behavior that is intentionally not covered
by the streaming suite. We validate: happy-path JSON (non‑SSE) response shape,
default `user_id` backfilling, validation error mapping (→400), content filter
and token limit error mappings (→406/413), and unexpected errors (→500).
All remote/service dependencies are monkeypatched to fakes.

Usage:
- Reuses `async_client` from `tests/test_streaming/conftest.py`.
- Patches `ingenious.api.routes.chat.get_chat_service` and
  `ingenious.api.routes.chat.get_conditional_security`.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import httpx
import pytest

from ingenious.errors.content_filter_error import ContentFilterError
from ingenious.errors.token_limit_exceeded_error import TokenLimitExceededError
from ingenious.models.chat import ChatRequest, ChatResponse


DEFAULT_USER_ID = "unspecified_user"
JSON_MEDIA_TYPE_SUBSTR = "application/json"
SSE_MEDIA_TYPE = "text/event-stream"


class _FakeNonstreamService:
    """Fake ChatService used by the non‑streaming route tests."""

    def __init__(self, responder: Optional[Callable[[ChatRequest], Any]] = None) -> None:
        """Create a fake that returns a ChatResponse or raises as configured.

        Args:
            responder: Optional callable to produce a response or raise.
        """
        self._responder = responder
        self.last_request: Optional[ChatRequest] = None

    async def get_chat_response(self, chat_request: ChatRequest) -> ChatResponse:
        """Return a response or raise via the configured responder."""
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


def _patch_common_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    """Silence namespace scanning and bypass auth guard for tests."""
    import ingenious.api.routes.chat as chat_mod

    def _noop(*_args: object, **_kwargs: object) -> None:
        return None

    def _dummy_security() -> str:
        return "tester"

    monkeypatch.setattr(chat_mod.ns_utils, "print_namespace_modules", _noop)
    monkeypatch.setattr(chat_mod, "get_conditional_security", _dummy_security)


@pytest.mark.anyio
async def test_nonstream_happy_path_json_response(async_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """It returns 200 JSON (non‑SSE) with required ChatResponse fields."""
    import ingenious.api.routes.chat as chat_mod

    _patch_common_dependencies(monkeypatch)

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
    monkeypatch.setattr(chat_mod, "get_chat_service", lambda: fake)

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
async def test_nonstream_default_user_id_backfill(async_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Route fills missing `user_id` with DEFAULT_USER_ID before delegating."""
    import ingenious.api.routes.chat as chat_mod

    _patch_common_dependencies(monkeypatch)

    fake = _FakeNonstreamService()
    monkeypatch.setattr(chat_mod, "get_chat_service", lambda: fake)

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
async def test_nonstream_validation_error_400(async_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing `conversation_flow` triggers HTTP 400 with value error detail."""
    import ingenious.api.routes.chat as chat_mod

    _patch_common_dependencies(monkeypatch)
    monkeypatch.setattr(chat_mod, "get_chat_service", lambda: _FakeNonstreamService())

    payload = {
        "user_prompt": "hi",
        # conversation_flow intentionally omitted
    }
    resp = await async_client.post("/api/v1/chat", json=payload)
    assert resp.status_code == 400
    assert "conversation_flow not set" in resp.json().get("detail", "")


@pytest.mark.anyio
async def test_nonstream_error_mapping_406_and_413(async_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """ContentFilterError→406 and TokenLimitExceededError→413 are mapped."""
    import ingenious.api.routes.chat as chat_mod

    _patch_common_dependencies(monkeypatch)

    # 406 mapping
    fake_406 = _FakeNonstreamService(responder=lambda _r: ContentFilterError("blocked"))
    monkeypatch.setattr(chat_mod, "get_chat_service", lambda: fake_406)
    payload: dict[str, Any] = {
        "user_prompt": "hi",
        "conversation_flow": "classification_agent",
    }
    resp = await async_client.post("/api/v1/chat", json=payload)
    assert resp.status_code == 406
    assert "Content filtered" in resp.json().get("detail", "")

    # 413 mapping
    fake_413 = _FakeNonstreamService(responder=lambda _r: TokenLimitExceededError("too long"))
    monkeypatch.setattr(chat_mod, "get_chat_service", lambda: fake_413)
    resp = await async_client.post("/api/v1/chat", json=payload)
    assert resp.status_code == 413
    assert "Token limit exceeded" in resp.json().get("detail", "")


@pytest.mark.anyio
async def test_nonstream_unexpected_error_500(async_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Unexpected exception is mapped to HTTP 500 with message (no traceback)."""
    import ingenious.api.routes.chat as chat_mod

    _patch_common_dependencies(monkeypatch)

    fake_500 = _FakeNonstreamService(responder=lambda _r: RuntimeError("boom"))
    monkeypatch.setattr(chat_mod, "get_chat_service", lambda: fake_500)
    payload = {
        "user_prompt": "hi",
        "conversation_flow": "classification_agent",
    }
    resp = await async_client.post("/api/v1/chat", json=payload)
    assert resp.status_code == 500
    body = resp.json().get("detail", "")
    assert "boom" in body
    assert "Traceback" not in body
