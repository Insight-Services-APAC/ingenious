# tests/test_streaming/test_multi_agent_nonstreaming.py
"""multi_agent.service non‑streaming behavior (complementary tests).

Scenarios:
1) Built‑in flow disabled → `_load_conversation_flow_class` raises ValueError.
2) Static method flow returning `(text, memory)` is converted to `ChatResponse`
   and persists history because this path is non‑streaming.
3) `_prepare_chat_request` topic coercion: comma‑separated string → list of
   trimmed items; also thread_id is set when missing.

We inject minimal custom flows via patching the importer used by the service.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, AsyncIterator, List, Optional

import pytest

from ingenious.models.chat import ChatRequest, ChatResponse, ChatResponseChunk
from ingenious.services.chat_services.multi_agent.service import multi_agent_chat_service


@dataclass
class _RecordedMessage:
    """Simple record for captured writes in the fake repository."""
    role: str
    content: str


class _RecorderRepo:
    """Fake ChatHistoryRepository that records calls for assertions."""

    def __init__(self) -> None:
        """Initialize empty logs."""
        self.messages: list[_RecordedMessage] = []
        self.memories: list[_RecordedMessage] = []

    async def add_message(self, msg: Any) -> str:
        """Record a message write and return a fake id."""
        self.messages.append(_RecordedMessage(role=getattr(msg, "role", ""), content=getattr(msg, "content", "")))
        return "msg-id"

    async def add_memory(self, msg: Any) -> str:
        """Record a memory write and return a fake id."""
        self.memories.append(_RecordedMessage(role=getattr(msg, "role", ""), content=getattr(msg, "content", "")))
        return "mem-id"

    async def get_thread_messages(self, _thread_id: str) -> list[Any]:
        """No prior history for these tests."""
        return []


class _StaticFlow:
    """Custom static flow used to validate non‑streaming conversion + coercion."""

    # External holder to capture topics for test 3
    captured_topics: list[str] = []

    @staticmethod
    async def get_conversation_response(
        message: str,
        topics: Optional[list[str]] = None,
        thread_memory: str = "",
        memory_record_switch: bool = True,
        thread_chat_history: Optional[list[dict[str, str]]] = None,
    ) -> tuple[str, str]:
        """Return text and memory, capturing `topics` for assertions."""
        _ = (message, thread_memory, memory_record_switch, thread_chat_history)  # unused
        _StaticFlow.captured_topics = topics or []
        return "STATIC-REPLY", "STATIC-MEM"


def _make_config(enable_builtins: bool = True) -> Any:
    """Return a minimal config satisfying the service constructor."""
    chat_service_cfg = SimpleNamespace(enable_builtin_workflows=enable_builtins)
    # `openai_service_instance` is required by ctor; we only need a placeholder.
    return SimpleNamespace(chat_service=chat_service_cfg, openai_service_instance=object())


def _patch_importer(monkeypatch: pytest.MonkeyPatch, flow_cls: Any) -> None:
    """Patch the module-level importer used by the service to return our class."""
    monkeypatch.setattr(
        "ingenious.services.chat_services.multi_agent.service.import_class_with_fallback",
        lambda *_args, **_kwargs: flow_cls,
    )


@pytest.mark.anyio
async def test_builtin_flow_disabled_raises(make_min_multi_config: Any) -> None:
    """Disabling built‑ins rejects requests that target a built‑in flow."""
    # Use provided helper for a realistic config; then disable built-ins.
    config = make_min_multi_config()
    config.chat_service.enable_builtin_workflows = False

    repo = _RecorderRepo()
    svc = multi_agent_chat_service(config=config, chat_history_repository=repo, conversation_flow="classification_agent")

    req = ChatRequest(user_id="u1", user_prompt="hello", conversation_flow="classification_agent")
    with pytest.raises(ValueError) as exc:
        await svc.get_chat_response(req)
    assert "Built-in workflow 'classification_agent' is disabled" in str(exc.value)


@pytest.mark.anyio
async def test_static_tuple_converted_and_persisted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Static `(text, memory)` is converted to `ChatResponse` and persisted."""
    repo = _RecorderRepo()
    config = _make_config(enable_builtins=True)
    svc = multi_agent_chat_service(config=config, chat_history_repository=repo, conversation_flow="custom_static_flow")
    _patch_importer(monkeypatch, _StaticFlow)

    req = ChatRequest(user_id="user-1", user_prompt="Hi there", conversation_flow="custom_static_flow")
    resp = await svc.get_chat_response(req)

    # Response shape assertions
    assert isinstance(resp, ChatResponse)
    assert resp.agent_response == "STATIC-REPLY"
    assert resp.memory_summary == "STATIC-MEM"
    assert resp.thread_id  # set by _prepare_chat_request
    assert resp.message_id

    # Persistence: user + assistant messages and one memory record
    roles = [m.role for m in repo.messages]
    contents = [m.content for m in repo.messages]
    assert roles == ["user", "assistant"]
    assert contents[0] == "Hi there"
    assert contents[1] == "STATIC-REPLY"
    assert [m.role for m in repo.memories] == ["memory_assistant"]
    assert repo.memories[0].content == "STATIC-MEM"


@pytest.mark.anyio
async def test_topic_coercion_and_thread_id_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Comma‑separated `topic` string is normalized to a trimmed list; thread_id is set."""
    repo = _RecorderRepo()
    config = _make_config(enable_builtins=True)
    svc = multi_agent_chat_service(config=config, chat_history_repository=repo, conversation_flow="topic_flow")
    _patch_importer(monkeypatch, _StaticFlow)

    req = ChatRequest(user_id="u1", user_prompt="Hello", conversation_flow="topic_flow", topic="a,  b, c  ")
    resp = await svc.get_chat_response(req)

    # Topics captured by the static flow reflect `_prepare_chat_request` coercion.
    assert _StaticFlow.captured_topics == ["a", "b", "c"]
    # Thread id was generated because it was omitted in the request.
    assert resp.thread_id and isinstance(resp.thread_id, str)
