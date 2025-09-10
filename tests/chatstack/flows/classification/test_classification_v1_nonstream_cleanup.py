"""Classification v1 non-stream: client close on exception.

This test verifies that `get_conversation_response` in the v1 classification
agent closes the model client even when the underlying `AssistantAgent`
raises an exception.

Why:
Covers cleanup/resource-management guarantees on the failure path.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import patch

import pytest

from ingenious.services.chat_services.multi_agent.conversation_flows.classification_agent.classification_agent import (  # noqa: E501
    ConversationFlow,
)

MESSAGE: str = "hi"
FALLBACK_PREFIX: str = "Category: payload_type_1"


class _SpyClient:
    """Spy client that records close() calls."""

    def __init__(self) -> None:
        self.closed: bool = False

    async def close(self) -> None:
        """Mark as closed; used to assert cleanup on exception."""
        self.closed = True


class _BoomAgent:
    """AssistantAgent stub that always raises on on_messages()."""

    def __init__(self, *_: object, **__: object) -> None:
        """No-op init to satisfy construction."""
        return

    async def on_messages(self, *_: object, **__: object) -> object:  # pragma: no cover
        """Always raise to trigger fallback/cleanup path."""
        raise RuntimeError("agent failed")


class _DummyHandler(logging.Handler):
    """Logging handler stub to satisfy LLM usage tracker slot."""

    def emit(self, _record: logging.LogRecord) -> None:  # pragma: no cover
        """No-op emit implementation."""
        return


class _ModelCfg:
    """Minimal model config; values are not used by the spy client."""

    model: str = "m"
    api_key: str = "k"
    base_url: str = "u"
    deployment: str = "d"
    api_version: str = "v"
    authentication_method: str = "azure"


class _Cfg:
    """Minimal global config with a single model entry."""

    models: list[_ModelCfg] = [_ModelCfg()]


@pytest.mark.anyio
async def test_classification_v1_nonstream_exception_closes_model_client() -> None:
    """Ensure model_client.close() is awaited when the agent raises."""
    spy = _SpyClient()

    with patch(
        # Return the spy client so we can assert close() was called.
        "ingenious.client.azure.AzureClientFactory.create_openai_chat_completion_client",
        return_value=spy,
    ), patch(
        # Replace AssistantAgent used by the module with our raising stub.
        "ingenious.services.chat_services.multi_agent.conversation_flows.classification_agent.classification_agent.AssistantAgent",  # noqa: E501
        new=_BoomAgent,
    ), patch(
        # Provide a dummy LLMUsageTracker compatible with logging.Handler.
        "ingenious.services.chat_services.multi_agent.conversation_flows.classification_agent.classification_agent.LLMUsageTracker",  # noqa: E501
        new=_DummyHandler,
    ), patch(
        # Provide a minimal config object to satisfy get_config().
        "ingenious.services.chat_services.multi_agent.conversation_flows.classification_agent.classification_agent.config.get_config",  # noqa: E501
        return_value=_Cfg(),
    ):
        text, _mem = await ConversationFlow.get_conversation_response(
            message=MESSAGE,
            topics=None,
            thread_memory="",
            memory_record_switch=True,
            thread_chat_history=None,
            chatrequest=None,
        )

    # Fallback text is returned and client is closed.
    assert text.startswith(FALLBACK_PREFIX)
    assert spy.closed is True
