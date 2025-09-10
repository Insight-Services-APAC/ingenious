from __future__ import annotations

"""SQL non-streaming and ChatService validation tests.

Why:
    - Cover SQL flow's non-streaming API (SQLite fallback) to ensure response
      shape and safe token accounting.
    - Validate ChatService rejects missing conversation_flow early.

Usage:
    `pytest -q tests/test_additional/test_sql_nonstream_and_chatservice_validation.py`
"""

from types import SimpleNamespace
from typing import Any, Callable

import pytest

from ingenious.models.chat import ChatRequest
from ingenious.services.chat_service import ChatService
from ingenious.services.chat_services.multi_agent.conversation_flows.sql_manipulation_agent.sql_manipulation_agent import (  # noqa: E501
    ConversationFlow as SQLFlow,
)

PROMPT_COLUMNS: str = "What columns are available?"
USER_ID: str = "u"
THREAD_ID: str = "t"
FLOW_SQL: str = "sql_manipulation_agent"
FLOW_CLASSIFICATION: str = "classification_agent"


class _StubParent:
    """Minimal parent carrying `config` and optional repository."""

    def __init__(self, cfg: Any) -> None:
        self.config = cfg
        self.chat_history_repository = None


class _DummyMemMgr:
    """No-op memory manager used to bypass external dependencies."""

    def maintain_memory(self, _new_content: str, _max_words: int = 150) -> None:
        """No-op maintenance hook (never raises)."""
        return None


@pytest.mark.asyncio
async def test_sql_agent_nonstream_happy_path_sqlite(
    monkeypatch: pytest.MonkeyPatch,
    patch_autogen_stack: None,
    stub_openai_factory: None,
    make_min_multi_config: Any,
) -> None:
    """Non-streaming SQL flow returns a sensible ChatResponse via SQLite fallback.

    Intent:
        Exercise the one-shot path: ensure agent_response is non-empty and token
        fields are integers ≥ 0. The fallback to SQLite is used when Azure SQL
        is not configured.
    """
    # Patch memory manager used by IConversationFlow base initializer.
    from ingenious.services.chat_services.multi_agent import service as ma_service

    def _fake_get_memory_manager(_cfg: Any, _path: str) -> _DummyMemMgr:
        return _DummyMemMgr()

    monkeypatch.setattr(ma_service, "get_memory_manager", _fake_get_memory_manager)

    cfg = make_min_multi_config(conversation_flow=FLOW_SQL)
    flow = SQLFlow(parent_multi_agent_chat_service=_StubParent(cfg))

    req = ChatRequest(
        user_prompt=PROMPT_COLUMNS,
        conversation_flow=FLOW_SQL,
        user_id=USER_ID,
        thread_id=THREAD_ID,
    )
    resp = await flow.get_conversation_response(req)
    assert getattr(resp, "agent_response", "") != ""
    assert isinstance(resp.token_count, int) and resp.token_count >= 0
    assert isinstance(resp.max_token_count, int) and resp.max_token_count >= 0


@pytest.mark.asyncio
async def test_chat_service_requires_conversation_flow(
    monkeypatch: pytest.MonkeyPatch, make_min_multi_config: Any
) -> None:
    """Validation: get_chat_response must reject empty conversation_flow.

    Intent:
        Ensure `ChatService.get_chat_response` raises `ValueError` before
        delegating to backend when `conversation_flow` is not set.
    """

    # Patch importer to a benign backend class so ChatService can be constructed.
    from ingenious.services import chat_service as cs_mod

    class _DummyBackend:
        def __init__(
            self, config: Any, chat_history_repository: Any, conversation_flow: str
        ) -> None:
            self.config = config
            self.chat_history_repository = chat_history_repository
            self.conversation_flow = conversation_flow

        async def get_chat_response(self, *_: Any, **__: Any) -> Any:
            """Not used in this test; provided for completeness."""
            return None

    def _fake_importer(*_: Any, **__: Any) -> Callable[..., Any]:
        return _DummyBackend

    monkeypatch.setattr(cs_mod, "import_class_with_fallback", _fake_importer)

    cfg = make_min_multi_config(conversation_flow=FLOW_CLASSIFICATION)
    svc = ChatService(
        chat_service_type="multi_agent",
        chat_history_repository=None,  # not used by this validation path
        conversation_flow=FLOW_CLASSIFICATION,
        config=cfg,
    )

    with pytest.raises(ValueError) as excinfo:
        bad = ChatRequest(
            user_prompt="x", conversation_flow="", user_id=USER_ID, thread_id=THREAD_ID
        )
        await svc.get_chat_response(bad)

    assert "conversation_flow not set" in str(excinfo.value)
