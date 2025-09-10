"""Classification (non-stream) exception fallback test.

Why:
- Ensure deterministic fallback message and memory summary when agent fails.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from ingenious.models.chat import ChatRequest
from ingenious.services.chat_services.multi_agent.conversation_flows.classification_agent import (  # type: ignore[attr-defined]  # noqa: E501
    classification_agent as clf_mod,
)

PROMPT: str = "hello"


class _BoomAgent:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Simulate agent that raises during on_messages."""
        return

    async def on_messages(self, *_a: Any, **_k: Any) -> object:
        """Always raise to trigger fallback path."""
        raise RuntimeError("LLM down")


class _DummyHandler(logging.Handler):
    def __init__(self, *_a: Any, **_k: Any) -> None:
        super().__init__()


class _DummyClient:
    async def close(self) -> None:  # ensure awaited close works
        return None


@pytest.mark.asyncio
async def test_classification_agent_nonstream_exception_fallback_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-stream path must return the documented fallback when agent fails."""
    # Patch assistant, usage tracker (logging.Handler), and client factory.
    monkeypatch.setattr(clf_mod, "AssistantAgent", _BoomAgent, raising=True)
    monkeypatch.setattr(clf_mod, "LLMUsageTracker", _DummyHandler, raising=True)
    monkeypatch.setattr(
        clf_mod.AzureClientFactory,
        "create_openai_chat_completion_client",
        lambda _cfg: _DummyClient(),
        raising=True,
    )

    # Minimal config access inside flow
    monkeypatch.setattr(
        clf_mod.config,
        "get_config",
        lambda: type("C", (), {"models": [type("M", (), {})]})(),
        raising=True,
    )

    text, mem = await clf_mod.ConversationFlow.get_conversation_response(
        message=PROMPT,
        chatrequest=ChatRequest(user_prompt=PROMPT, conversation_flow="classification_agent"),
    )
    assert text.startswith("Category: payload_type_1")
    assert mem.startswith("Classification error handled:")
