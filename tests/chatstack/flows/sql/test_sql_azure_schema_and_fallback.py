"""SQL agent: cover Azure (pyodbc) schema path and empty-schema fallback.

These tests exercise the non-streaming initialization that inspects Azure SQL
schema via pyodbc and builds a FunctionTool description. We capture that
description to assert whether the Azure or SQLite branch was taken.
"""

from __future__ import annotations

import types
from typing import Any, List

import pytest

from ingenious.models.chat import ChatRequest
from ingenious.services.chat_services.multi_agent.conversation_flows.sql_manipulation_agent.sql_manipulation_agent import (  # noqa: E501
    ConversationFlow,
)


class _Recorder:
    """Helper to capture the most recent FunctionTool description."""

    def __init__(self) -> None:
        self.descriptions: List[str] = []

    def factory(self) -> Any:
        """Return a fake FunctionTool type that records description.

        IMPORTANT: capture `self` via closure (no module-level globals).
        """
        recorder = self

        class _FT:
            def __init__(self, _callable: Any, *, description: str) -> None:
                self.callable = _callable
                self.description = description
                recorder.descriptions.append(description)

        return _FT


@pytest.mark.asyncio
async def test_sql_agent_azure_schema_detected_and_used(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """With non-empty Azure schema, branch should reference Azure SQL + columns."""
    # Patch memory manager to prevent side effects.
    monkeypatch.setattr(
        "ingenious.services.chat_services.multi_agent.service.get_memory_manager",
        lambda _cfg, _path: types.SimpleNamespace(
            maintain_memory=lambda *_a, **_k: None
        ),
    )

    # Minimal parent config with Azure SQL settings.
    class _AzureSQL:
        database_connection_string = "Driver=ODBC;Server=.;Database=db;"
        table_name = "t"

    class _Cfg:
        def __init__(self, root: str) -> None:
            self.chat_history = types.SimpleNamespace(memory_path=root)
            self.models = [types.SimpleNamespace(model="stub")]
            self.azure_sql_services = _AzureSQL()

    class _Parent:
        def __init__(self, cfg: Any) -> None:
            self.config = cfg

    # Stub AssistantAgent and OpenAI client.
    class _DummyClient:
        async def close(self) -> None:  # pragma: no cover - best-effort close
            return None

    class _Resp:
        def __init__(self) -> None:
            self.chat_message = types.SimpleNamespace(content="OK")

    class _Agent:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

        async def on_messages(self, *args: Any, **kwargs: Any) -> Any:
            return _Resp()

    monkeypatch.setattr(
        "ingenious.client.azure.AzureClientFactory.create_openai_chat_completion_client",
        lambda _mc: _DummyClient(),
    )
    monkeypatch.setattr(
        "ingenious.services.chat_services.multi_agent.conversation_flows."
        "sql_manipulation_agent.sql_manipulation_agent.AssistantAgent",
        _Agent,
    )

    # Stub pyodbc.connect to return a cursor with two columns.
    class _Cursor:
        def __init__(self) -> None:
            self._called = False
            self.description = [("c1",), ("c2",)]

        def execute(self, *_a: Any, **_k: Any) -> None:
            self._called = True

        def fetchall(self) -> list[tuple[str]]:
            # First call (schema) returns two column names.
            return [("c1",), ("c2",)]

    class _Conn:
        def __enter__(self) -> "_Conn":
            return self

        def __exit__(self, *_a: Any, **_k: Any) -> None:
            return None

        def cursor(self) -> _Cursor:
            return _Cursor()

    monkeypatch.setattr(
        "ingenious.services.chat_services.multi_agent.conversation_flows."
        "sql_manipulation_agent.sql_manipulation_agent.pyodbc",
        types.SimpleNamespace(connect=lambda _cs: _Conn()),
    )
    monkeypatch.setattr(
        "ingenious.services.chat_services.multi_agent.conversation_flows."
        "sql_manipulation_agent.sql_manipulation_agent.PYODBC_AVAILABLE",
        True,
    )

    # Capture FunctionTool description (use a local recorder).
    rec = _Recorder()
    monkeypatch.setattr(
        "ingenious.services.chat_services.multi_agent.conversation_flows."
        "sql_manipulation_agent.sql_manipulation_agent.FunctionTool",
        rec.factory(),
    )

    flow = ConversationFlow(parent_multi_agent_chat_service=_Parent(_Cfg(str(tmp_path))))
    req = ChatRequest(
        user_prompt="describe schema", conversation_flow="sql_manipulation_agent"
    )
    res = await flow.get_conversation_response(req)
    assert res.agent_response == "OK"
    assert rec.descriptions, "FunctionTool should have been constructed."
    desc = rec.descriptions[-1]
    assert "Azure SQL Database" in desc
    assert "columns: c1, c2" in desc


@pytest.mark.asyncio
async def test_sql_agent_empty_azure_schema_falls_back_to_sqlite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """Empty INFORMATION_SCHEMA → use SQLite branch with known demo columns."""
    # Patch memory manager.
    monkeypatch.setattr(
        "ingenious.services.chat_services.multi_agent.service.get_memory_manager",
        lambda _cfg, _path: types.SimpleNamespace(
            maintain_memory=lambda *_a, **_k: None
        ),
    )

    class _AzureSQL:
        database_connection_string = "Driver=ODBC;Server=.;Database=db;"
        table_name = "t"

    class _Cfg:
        def __init__(self, root: str) -> None:
            self.chat_history = types.SimpleNamespace(memory_path=root)
            self.models = [types.SimpleNamespace(model="stub")]
            self.azure_sql_services = _AzureSQL()

    class _Parent:
        def __init__(self, cfg: Any) -> None:
            self.config = cfg

    class _DummyClient:
        async def close(self) -> None:
            return None

    class _Resp:
        def __init__(self) -> None:
            self.chat_message = types.SimpleNamespace(content="OK")

    class _Agent:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

        async def on_messages(self, *args: Any, **_k: Any) -> Any:
            return _Resp()

    monkeypatch.setattr(
        "ingenious.client.azure.AzureClientFactory.create_openai_chat_completion_client",
        lambda _mc: _DummyClient(),
    )
    monkeypatch.setattr(
        "ingenious.services.chat_services.multi_agent.conversation_flows."
        "sql_manipulation_agent.sql_manipulation_agent.AssistantAgent",
        _Agent,
    )

    # pyodbc.connect returns a cursor with empty schema (forces fallback).
    class _Cursor:
        def __init__(self) -> None:
            self.description = []

        def execute(self, *_a: Any, **_k: Any) -> None:
            return None

        def fetchall(self) -> list[tuple[str]]:
            return []

    class _Conn:
        def __enter__(self) -> "_Conn":
            return self

        def __exit__(self, *_a: Any, **_k: Any) -> None:
            return None

        def cursor(self) -> _Cursor:
            return _Cursor()

    monkeypatch.setattr(
        "ingenious.services.chat_services.multi_agent.conversation_flows."
        "sql_manipulation_agent.sql_manipulation_agent.pyodbc",
        types.SimpleNamespace(connect=lambda _cs: _Conn()),
    )
    monkeypatch.setattr(
        "ingenious.services.chat_services.multi_agent.conversation_flows."
        "sql_manipulation_agent.sql_manipulation_agent.PYODBC_AVAILABLE",
        True,
    )

    # Capture FunctionTool description (local recorder again).
    rec = _Recorder()
    monkeypatch.setattr(
        "ingenious.services.chat_services.multi_agent.conversation_flows."
        "sql_manipulation_agent.sql_manipulation_agent.FunctionTool",
        rec.factory(),
    )

    flow = ConversationFlow(parent_multi_agent_chat_service=_Parent(_Cfg(str(tmp_path))))
    req = ChatRequest(
        user_prompt="describe schema", conversation_flow="sql_manipulation_agent"
    )
    res = await flow.get_conversation_response(req)
    assert res.agent_response == "OK"
    assert rec.descriptions, "FunctionTool should have been constructed."
    desc = rec.descriptions[-1]
    assert "SQLite database" in desc
    # Presence of a couple of demo columns is sufficient to prove fallback.
    assert "parental_education" in desc
    assert "writing_score" in desc
