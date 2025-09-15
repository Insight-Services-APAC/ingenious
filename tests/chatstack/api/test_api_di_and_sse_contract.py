# tests/chatstack/api/test_api_di_and_sse_contract.py
import json
import pytest
from fastapi.testclient import TestClient

from ingenious.main.app_factory import create_app
from ingenious.config.main_settings import IngeniousSettings
from ingenious.models.chat import ChatResponse, ChatResponseChunk

# 👇 import overrides from the SAME module the routes use
from ingenious.services.fastapi_dependencies import (
    get_chat_service as _get_chat_service,
    get_conditional_security as _get_conditional_security,
    get_config as _get_config,
)

# ----- Stub used by all tests ------------------------------------------------
class StubChatService:
    async def get_chat_response(self, chat_request):
        return ChatResponse(
            thread_id="t1",
            message_id="m1",
            agent_response="OK",
            token_count=0,
            max_token_count=0,
            memory_summary=None,
        )

    async def get_streaming_chat_response(self, chat_request):
        # one content chunk then a final chunk (mirrors real behavior)
        yield ChatResponseChunk(
            thread_id="t1",
            message_id="m1",
            chunk_type="content",
            content="hello",
            is_final=False,
        )
        yield ChatResponseChunk(
            thread_id="t1",
            message_id="m1",
            chunk_type="final",
            token_count=0,
            max_token_count=0,
            is_final=True,
        )

# ----- Fixtures --------------------------------------------------------------
@pytest.fixture(scope="function")
def app(monkeypatch, tmp_path):
    # App factory will chdir into this
    monkeypatch.setenv("INGENIOUS_WORKING_DIR", str(tmp_path))

    # Build a minimal, env-independent config and app
    settings = IngeniousSettings.create_minimal_config()
    app = create_app(settings)

    # Override DI dependencies used by the routes
    app.dependency_overrides[_get_chat_service] = lambda: StubChatService()

    # Return a fixed username; avoids reading Authorization headers and configuration
    def _username() -> str:
        return "test-user"

    app.dependency_overrides[_get_conditional_security] = _username

    # If anything else asks for config through this dependency, return our minimal one
    app.dependency_overrides[_get_config] = lambda: settings

    try:
        yield app
    finally:
        app.dependency_overrides.clear()

@pytest.fixture(scope="function")
def client(app):
    with TestClient(app) as c:
        yield c

# ----- Helper ---------------------------------------------------------------
def _collect_sse_frames(resp):
    frames = []
    for ln in resp.iter_lines():
        if isinstance(ln, bytes):
            ln = ln.decode()
        if ln.startswith("data: "):
            frames.append(json.loads(ln[6:]))
    return frames

# ----- Tests ----------------------------------------------------------------
def test_nonstream_ok(client):
    r = client.post(
        "/api/v1/chat",
        json={
            "conversation_flow": "classification-agent",
            "user_prompt": "Classify payload_type_1",
            "stream": False,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["agent_response"] == "OK"

def test_stream_ok_and_done(client):
    with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={
            "conversation_flow": "classification-agent",
            "user_prompt": "Stream it",
            "stream": True,
        },
    ) as r:
        # FastAPI/Starlette may append charset; keep the check permissive
        assert r.headers["content-type"].startswith("text/event-stream")
        frames = _collect_sse_frames(r)
        assert any(f.get("event") == "data" for f in frames), frames
        assert frames[-1].get("event") == "done", frames

def test_stream_validation_error_then_done(client):
    with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"conversation_flow": "", "user_prompt": "x", "stream": True},
    ) as r:
        frames = _collect_sse_frames(r)
        assert frames[0].get("event") == "error", frames
        assert frames[-1].get("event") == "done", frames
