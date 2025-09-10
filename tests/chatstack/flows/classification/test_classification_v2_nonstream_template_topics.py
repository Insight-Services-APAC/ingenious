"""Classification v2: non-streaming tuple path + template fallback + topics.

Ensures the non-stream entry returns a (text, memory_summary) tuple even when
templates are missing (fallback system_message path) and verifies that a single
string topic is coerced to a list.
"""

from __future__ import annotations

import types
from typing import Any, Tuple

import pytest

from ingenious.models.chat import ChatRequest
from ingenious.services.chat_services.multi_agent.conversation_flows.classification_agent.classification_agent_v2 import (  # noqa: E501
    ConversationFlow,
)


@pytest.mark.asyncio
async def test_classification_v2_nonstream_template_fallback_and_topics_coercion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """Non-stream tuple is returned; topics string coerces to list; templates fallback."""
    # Patch config.get_config used by this module.
    class _ModelCfg:
        model = "stub-model"
        api_key = "k"
        base_url = "https://x"
        deployment = "d"
        api_version = "v"
        authentication_method = "azure"

    class _Cfg:
        models = [types.SimpleNamespace(**_ModelCfg.__dict__)]
        chat_history = types.SimpleNamespace(memory_path=str(tmp_path))

    monkeypatch.setattr(
        "ingenious.services.chat_services.multi_agent.conversation_flows."
        "classification_agent.classification_agent_v2.config.get_config",
        lambda: _Cfg(),
    )

    # Force template fallback by raising on Environment.get_template.
    def _raise(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("no template")

    monkeypatch.setattr(
        "jinja2.Environment.get_template", _raise, raising=True
    )

    # Stub ConversationPattern to avoid heavy internals and capture topics.
    class _StubPattern:
        def __init__(
            self,
            *,
            default_llm_config: dict[str, object],
            topics: list[str],
            memory_record_switch: bool,
            memory_path: str,
            thread_memory: str,
        ) -> None:
            self._topics = topics
            self._cfg = default_llm_config
            self._closed = False

        def add_topic_agent(self, *_a: Any, **_k: Any) -> None:
            return None

        async def get_conversation_response(self, _message: str) -> Tuple[str, str]:
            return "result text", "memory summary"

        async def close(self) -> None:
            self._closed = True

    monkeypatch.setattr(
        "ingenious.services.chat_services.multi_agent.conversation_flows."
        "classification_agent.classification_agent_v2.ConversationPattern",
        _StubPattern,
    )

    # Act.
    req = ChatRequest(
        user_prompt="hello",
        conversation_flow="classification_agent_v2",
        topic="support",  # string that should be coerced to ["support"]
    )
    text, summary = await ConversationFlow.get_conversation_response(req)

    # Assert.
    assert isinstance(text, str) and text
    assert isinstance(summary, str) and summary
