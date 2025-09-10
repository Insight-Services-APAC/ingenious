"""KB local Chroma: query exception returns friendly 'Search error: ...'.

This test ensures `_search_local_chroma` surfaces concise error messages when
underlying Chroma collection query raises an exception.
"""

from __future__ import annotations

import os
import sys
import types

import pytest

from ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent.knowledge_base_agent import (  # noqa: E501
    ConversationFlow,
)
from ingenious.services.chat_services.multi_agent.service import (
    multi_agent_chat_service as _Parent,
)

TOP_K: int = 3


class _Cfg:
    """Config stub without Azure services to force local path."""

    class ChatHistory:
        memory_path: str = ".tmp"

    chat_history = ChatHistory()
    azure_search_services: list[object] = []
    openai_service_instance: object = object()


def _stub_parent() -> _Parent:
    """Create a minimal parent for the KB flow."""
    repo = types.SimpleNamespace(
        add_message=lambda *_: "id",
        add_memory=lambda *_: "id",
        get_thread_messages=lambda *_: [],
    )
    return _Parent(config=_Cfg(), chat_history_repository=repo, conversation_flow="kb")


class _Collection:
    """Stub Chroma collection that always raises from query."""

    def query(self, *_a: object, **_k: object) -> None:
        """Raise to simulate internal Chroma error."""
        raise RuntimeError("boom")


class _Client:
    """Stub Chroma PersistentClient that returns the raising collection."""

    def get_collection(self, *_a: object, **_k: object) -> _Collection:
        """Return our raising collection."""
        return _Collection()


@pytest.mark.anyio
async def test_kb_local_chroma_query_exception_returns_search_error_message(
    tmp_path: os.PathLike[str],
) -> None:
    """When Chroma query raises, flow returns 'Search error: ...' string."""
    # Install stub chromadb module.
    chroma_mod = types.ModuleType("chromadb")
    chroma_mod.PersistentClient = lambda *_, **__: _Client()
    sys.modules["chromadb"] = chroma_mod

    flow = ConversationFlow(parent_multi_agent_chat_service=_stub_parent())
    # Ensure the KB directory exists so we reach the query call.
    kb_dir = str(tmp_path)
    flow._kb_path = kb_dir  # type: ignore[attr-defined]

    result = await flow._search_local_chroma(
        search_query="q", top_k=TOP_K, logger=None  # type: ignore[arg-type]
    )
    assert result.startswith("Search error: ")
    assert "boom" in result
