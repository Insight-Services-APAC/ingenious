"""Multi-agent streaming import error surface test.

Why:
- When a flow cannot be imported, the stream must emit a single `error` chunk.
"""

from __future__ import annotations

import pytest

from ingenious.models.chat import ChatRequest
from ingenious.services.chat_services.multi_agent.service import (
    multi_agent_chat_service,
)

FLOW_NAME: str = "missing"
PROMPT: str = "x"


@pytest.mark.asyncio
async def test_multi_agent_streaming_import_error_yields_error_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing flow module should surface as an error chunk, not crash the stream."""
    cfg = type("Cfg", (), {"openai_service_instance": object()})()
    svc = multi_agent_chat_service(
        config=cfg,
        chat_history_repository=object(),  # not used in this path
        conversation_flow=FLOW_NAME,
    )

    def _boom(*_a: object, **_k: object) -> object:
        raise ImportError("no module")

    # Patch the imported symbol within the service module.
    monkeypatch.setattr(
        "ingenious.services.chat_services.multi_agent.service.import_class_with_fallback",
        _boom,
        raising=True,
    )

    req = ChatRequest(user_prompt=PROMPT, conversation_flow=FLOW_NAME)
    chunks = []
    async for ch in svc.get_streaming_chat_response(req):
        chunks.append(ch)

    assert len(chunks) == 1
    assert chunks[0].chunk_type == "error"
    assert "Conversation flow not found" in (chunks[0].content or "")
