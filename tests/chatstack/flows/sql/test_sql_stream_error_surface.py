"""SQL streaming should surface tool errors and still finalize.

Why:
- Ensures user-facing 'SQL Error:' content chunk and proper finalization.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

import pytest

from ingenious.models.chat import ChatRequest, ChatResponseChunk
from ingenious.services.chat_services.multi_agent.conversation_flows.sql_manipulation_agent import (  # type: ignore[attr-defined]  # noqa: E501
    sql_manipulation_agent as sql_mod,
)
from ingenious.services.chat_services.multi_agent.conversation_flows.sql_manipulation_agent.sql_manipulation_agent import (  # noqa: E501
    ConversationFlow as SQLFlow,
)

PROMPT: str = "please run a query"


class _ToolEvent:
    """Mimic a tool call event in the stream."""

    def __init__(self) -> None:
        self.event = "tool_call"


class _Msg:
    def __init__(self, content: str | None = None, usage: object | None = None) -> None:
        self.content = content
        self.usage = usage


class _DummyAgent:
    """Emit a tool event to trigger STATUS_EXECUTING, then an SQL error as text."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
        # Reflective behavior/tool wiring is irrelevant here.
        return

    def run_stream(self, *args: Any, **kwargs: Any) -> AsyncIterator[object]:
        async def _gen() -> AsyncIterator[object]:
            # Tool event first (gets filtered into a STATUS_EXECUTING status chunk).
            yield _ToolEvent()
            # The agent would normally narrate tool output; simulate an SQL error content.
            yield _Msg('SQL Error: near "SELECTT": syntax error')
        return _gen()


class _DummyClient:
    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_sql_agent_streaming_emits_sql_error_and_completes(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Streaming must surface SQL error content and still emit usage + final."""
    # Patch the assistant + client factory to avoid real LLM calls.
    monkeypatch.setattr(sql_mod, "AssistantAgent", _DummyAgent, raising=True)
    monkeypatch.setattr(
        sql_mod.AzureClientFactory,
        "create_openai_chat_completion_client",
        lambda _cfg: _DummyClient(),
        raising=True,
    )

    # Minimal parent config (force SQLite path).
    parent = type(
        "P",
        (),
        {
            "config": type(
                "Cfg",
                (),
                {
                    "chat_history": type("CH", (), {"memory_path": str(tmp_path)}),
                    "models": [type("M", (), {"model": "gpt-test"})],
                    "azure_sql_services": type("S", (), {"database_connection_string": "mock-connection-string"})(),  # noqa: E501
                },
            )(),
            "chat_history_repository": None,
        },
    )()

    flow = SQLFlow(parent_multi_agent_chat_service=parent)
    req = ChatRequest(user_prompt=PROMPT, conversation_flow="sql_manipulation_agent")

    chunks: list[ChatResponseChunk] = []
    async for ch in flow.get_streaming_conversation_response(req):
        chunks.append(ch)

    types: list[str] = [c.chunk_type for c in chunks]
    assert "content" in types, "SQL error should be surfaced as content."
    assert any(
        (c.content or "").startswith("SQL Error:") for c in chunks if c.chunk_type == "content"
    )
    assert "usage" in types and "final" in types, "Stream must still finalize cleanly."
    assert types.index("usage") < types.index("final")
