"""Classification v1 memory precedence & history preview tests.

This module verifies two correctness-critical behaviors in the v1 classification
flow's non-streaming path:
1) `thread_memory` takes precedence over `thread_chat_history` when both exist.
2) When only history is present, the preview contains the last N entries with
   the expected "role: {truncated_content}..." format.

Usage:
- Patches Azure client and AssistantAgent to avoid external calls.
- Captures the constructed `system_message` for assertions.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

from ingenious.models.chat import ChatRequest
from ingenious.services.chat_services.multi_agent.conversation_flows.classification_agent.classification_agent import (  # noqa: E501
    ConversationFlow as V1Flow,
)

PREVIEW_COUNT: int = 10
OVERRIDE_TEXT: str = "OVERRIDE_MEMORY"
HISTORY_CONTENT: str = "old msg"


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


class _SpyAssistant:
    """Spy Assistant that records the system_message passed to the agent."""

    seen_messages: ClassVar[list[str]] = []

    def __init__(self, *, system_message: str, **_: Any) -> None:
        """Record the prompt and ignore other kwargs."""
        type(self).seen_messages.append(system_message)

    async def on_messages(self, **__: Any) -> Any:
        """Return a minimal response object with a chat_message.content."""
        return SimpleNamespace(chat_message=SimpleNamespace(content="ok"))


@pytest.mark.anyio
async def test_classification_v1_memory_context_precedence_and_history_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assert (a) thread_memory precedence, (b) history preview format and window."""
    # Patch external dependencies with safe stubs.
    monkeypatch.setattr(
        "ingenious.client.azure.AzureClientFactory.create_openai_chat_completion_client",
        lambda *_a, **_k: _StubClient(),
        raising=True,
    )
    monkeypatch.setattr(
        "autogen_agentchat.agents.AssistantAgent",
        _SpyAssistant,
        raising=True,
    )
    monkeypatch.setattr(
        "ingenious.models.agent.LLMUsageTracker",
        _DummyHandler,
        raising=True,
    )

    # Synthetic history of > PREVIEW_COUNT items.
    history: list[dict[str, str]] = [
        {"role": "user", "content": HISTORY_CONTENT} for _ in range(PREVIEW_COUNT + 2)
    ]
    req = ChatRequest(user_prompt="hi", topic=["general"])

    # Case A: thread_memory present → it must override history preview.
    _SpyAssistant.seen_messages.clear()
    await V1Flow.get_conversation_response(
        message="ignored",
        thread_memory=OVERRIDE_TEXT,
        thread_chat_history=history,
        chatrequest=req,
    )
    sys_msg_a = _SpyAssistant.seen_messages[-1]
    assert OVERRIDE_TEXT in sys_msg_a, "Expected thread_memory to appear in system prompt"
    assert (
        f"user: {HISTORY_CONTENT}..." not in sys_msg_a
    ), "History preview must be ignored when thread_memory is set"

    # Case B: only history → preview must contain exactly the last PREVIEW_COUNT lines.
    _SpyAssistant.seen_messages.clear()
    await V1Flow.get_conversation_response(
        message="ignored",
        thread_memory="",
        thread_chat_history=history,
        chatrequest=req,
    )
    sys_msg_b = _SpyAssistant.seen_messages[-1]
    assert (
        "Previous conversation:" in sys_msg_b
    ), "Expected 'Previous conversation:' header in system prompt"
    assert (
        sys_msg_b.count(f"user: {HISTORY_CONTENT}...") == PREVIEW_COUNT
    ), "Expected preview of the last PREVIEW_COUNT entries with ellipsis"
