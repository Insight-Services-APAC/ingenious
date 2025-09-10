"""KB streaming should emit usage even when provider omits it.

Why:
- Guarantees a `usage` chunk for metrics stability (fallback heuristic).
"""

from __future__ import annotations

from typing import Any, AsyncIterator

import pytest

from ingenious.models.chat import ChatRequest, ChatResponseChunk
from ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent import (  # type: ignore[attr-defined]  # noqa: E501
    knowledge_base_agent as kb_mod,
)
from ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent.knowledge_base_agent import (  # noqa: E501
    ConversationFlow as KBFlow,
)

PROMPT: str = "hi"


class _Msg:
    def __init__(self, content: str) -> None:
        self.content = content


class _DummyAgent:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """No-op assistant; only provides a content-only stream."""
        return

    def run_stream(self, *args: Any, **kwargs: Any) -> AsyncIterator[_Msg]:
        """Yield content-only messages (no usage)."""
        async def _gen() -> AsyncIterator[_Msg]:
            yield _Msg("hello ")
            yield _Msg("world")
        return _gen()


class _DummyClient:
    async def close(self) -> None:
        """Satisfy `await model_client.close()` in the flow."""
        return None


@pytest.mark.asyncio
async def test_kb_stream_usage_emitted_when_provider_omits_usage(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Streaming should still emit a usage chunk if the provider never reports it."""
    # Patch AssistantAgent + client factory
    monkeypatch.setattr(kb_mod, "AssistantAgent", _DummyAgent, raising=True)
    monkeypatch.setattr(
        kb_mod.AzureClientFactory,
        "create_openai_chat_completion_client",
        lambda _cfg: _DummyClient(),
        raising=True,
    )

    # Minimal parent config
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
                    "azure_search_services": [],
                },
            )(),
            "chat_history_repository": None,
        },
    )()
    flow = KBFlow(parent_multi_agent_chat_service=parent)
    req = ChatRequest(user_prompt=PROMPT, conversation_flow="knowledge_base_agent")

    chunks: list[ChatResponseChunk] = []
    async for ch in flow.get_streaming_conversation_response(req):
        chunks.append(ch)

    kinds: list[str] = [c.chunk_type for c in chunks]
    assert "usage" in kinds and "final" in kinds
    assert kinds.index("usage") < kinds.index("final"), "usage must precede final"

    usage = next(c for c in chunks if c.chunk_type == "usage")
    assert isinstance(usage.token_count, int) and usage.token_count >= 1
