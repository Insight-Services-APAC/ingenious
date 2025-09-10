"""SQL tool output formatting tests (single, multi, empty result branches).

This module exercises the result-formatting branches in the SQL flow's
`execute_sql_tool`:
- Empty result → 'No results found.'
- Single row → stringified dict with all expected columns.
- Multiple rows → stringified list[dict], preview-capped to ROW_PREVIEW_LIMIT.

Usage:
- Stubs AssistantAgent to capture the registered FunctionTool and returns.
- Calls the captured tool callable directly with deterministic SQLite queries.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, ClassVar, Protocol, runtime_checkable
from types import SimpleNamespace

import pytest

from ingenious.models.chat import ChatRequest
from ingenious.services.chat_services.multi_agent.conversation_flows.sql_manipulation_agent.sql_manipulation_agent import (  # noqa: E501
    ConversationFlow as SQLFlow,
)

TABLE: str = "students_performance"
ROW_PREVIEW_LIMIT: int = 10


class _StubClient:
    """No-op model client to satisfy close() in the flow."""

    async def close(self) -> None:
        """Close the client without side effects."""
        return None


class _DummyHandler:
    """Minimal logging handler stub matching the LLMUsageTracker API."""

    def __init__(self, *_: object, **__: object) -> None:
        """Accept arbitrary ctor args to mimic LLMUsageTracker signature."""
        super().__init__()

    def emit(self, *_: object, **__: object) -> None:
        """No-op emit to satisfy logging.Handler interface."""
        return None


@runtime_checkable
class _ToolWrapper(Protocol):
    """Protocol for the spy FunctionTool to expose the underlying callable."""

    fn: Callable[[str], Awaitable[str]]  # async execute_sql_tool(query: str) -> str


class _SpyFunctionTool:
    """Spy wrapper that captures the provided callable as `.fn`."""

    def __init__(self, fn: Callable[[str], Awaitable[str]], **_: Any) -> None:
        """Store the async function for direct invocation in tests."""
        self.fn = fn


class _SpyAssistant:
    """Spy Assistant that records tools passed to the agent."""

    last_tools: ClassVar[list[_ToolWrapper]] = []

    def __init__(self, *, tools: list[Any], **_: Any) -> None:
        """Capture the provided tools list."""
        type(self).last_tools = tools  # type: ignore[assignment]

    async def on_messages(self, **__: Any) -> Any:
        """Return a minimal chat_message container."""
        ChatMsg = type("C", (), {"content": "ok"})
        return type("R", (), {"chat_message": ChatMsg()})()


@dataclass
class _Cfg:
    class ChatHistory:
        # Change this __init__ method
        def __init__(self, memory_path: str) -> None:
            self.memory_path = memory_path

    def __init__(self, memory_path: str) -> None:
        self.chat_history = self.ChatHistory(memory_path=memory_path)
        # Add file_storage to prevent the AttributeError from Fix #1
        self.file_storage = SimpleNamespace(data=SimpleNamespace(add_sub_folders=True))

@dataclass
class _Parent:
    """Parent stub to satisfy IConversationFlow initialization."""

    config: _Cfg
    chat_history_repository: Any = None


@pytest.mark.anyio
async def test_sql_execute_tool_formats_single_multi_and_empty_results(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert execute_sql_tool returns correct formats for empty/single/multi results."""
    # Patch external dependencies and agents/tools.
    monkeypatch.setattr(
        "ingenious.client.azure.AzureClientFactory.create_openai_chat_completion_client",
        lambda *_a, **_k: _StubClient(),
        raising=True,
    )
    monkeypatch.setattr(
        "ingenious.models.agent.LLMUsageTracker",
        _DummyHandler,
        raising=True,
    )
    monkeypatch.setattr(
        "autogen_core.tools.FunctionTool",
        _SpyFunctionTool,
        raising=True,
    )
    monkeypatch.setattr(
        "autogen_agentchat.agents.AssistantAgent",
        _SpyAssistant,
        raising=True,
    )

    # Construct the flow so it seeds the SQLite demo DB under tmp_path.
    cfg = _Cfg(memory_path=str(tmp_path))
    parent = _Parent(config=cfg)
    flow = SQLFlow(parent_multi_agent_chat_service=parent)

    # Trigger tool registration by running the non-streaming path once.
    req = ChatRequest(user_prompt="list rows", topic=["general"])
    await flow.get_conversation_response(req)

    # Retrieve the captured tool and its async function.
    assert _SpyAssistant.last_tools, "Expected SQL FunctionTool to be registered."
    tool = _SpyAssistant.last_tools[0]
    assert isinstance(tool, _ToolWrapper)
    run = tool.fn

    # 1) Empty result branch
    empty_res = await run(f"SELECT * FROM {TABLE} WHERE 1=2")
    assert empty_res == "No results found."

    # 2) Single row branch
    single_res = await run(f"SELECT * FROM {TABLE} LIMIT 1")
    one_row = ast.literal_eval(single_res)
    assert isinstance(one_row, dict)
    assert set(one_row.keys()) == {
        "parental_education",
        "lunch",
        "test_prep_course",
        "math_score",
        "reading_score",
        "writing_score",
    }

    # 3) Multi-row branch (preview-limited)
    multi_res = await run(f"SELECT * FROM {TABLE}")
    many_rows = ast.literal_eval(multi_res)
    assert isinstance(many_rows, list)
    assert len(many_rows) >= 2  # Should be more than one row in the seeded demo
    assert len(many_rows) <= ROW_PREVIEW_LIMIT
