"""KB policy prefer_local → Azure escalation on empty local results.

Validates that with KB_POLICY=prefer_local and KB_FALLBACK_ON_EMPTY=1, the flow
first attempts local Chroma (returning "No relevant information..."), then
escalates to Azure, producing an Azure-formatted result.
"""

from __future__ import annotations

import os
import types
from typing import Any, Dict, List

import pytest

from ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent.knowledge_base_agent import (  # noqa: E501
    ConversationFlow,
)


@pytest.mark.asyncio
async def test_kb_prefer_local_escalates_to_azure_on_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """When local returns 'No relevant information...', use Azure fallback."""
    # Patch memory manager to avoid side effects.
    monkeypatch.setattr(
        "ingenious.services.chat_services.multi_agent.service.get_memory_manager",
        lambda _cfg, _path: types.SimpleNamespace(
            maintain_memory=lambda *_a, **_k: None
        ),
    )

    # Minimal config & parent.
    class _AzureSvc:
        endpoint = "https://example.search.windows.net"
        index_name = "idx"
        key = "abc123"

    class _Cfg:
        def __init__(self, root: str) -> None:
            self.chat_history = types.SimpleNamespace(memory_path=root)
            self.models = [types.SimpleNamespace(model="stub")]
            self.azure_search_services = [_AzureSvc()]
            self.knowledge_base_policy = "prefer_local"

    class _Parent:
        def __init__(self, cfg: Any) -> None:
            self.config = cfg

    cfg = _Cfg(str(tmp_path))
    flow = ConversationFlow(parent_multi_agent_chat_service=_Parent(cfg))

    # Ensure KB directory exists (empty) so local path proceeds past missing-dir check.
    os.makedirs(flow._kb_path, exist_ok=True)

    # Install a fake 'chromadb' to produce "No relevant information..." result.
    class _FakeCollection:
        def query(self, *, query_texts: List[str], n_results: int) -> Dict[str, Any]:
            return {"documents": [[]]}  # forces "No relevant information..." branch

    class _FakeClient:
        def __init__(self, *, path: str) -> None:
            self._path = path

        def get_collection(self, *, name: str) -> _FakeCollection:
            return _FakeCollection()

    chroma_mod = types.SimpleNamespace(PersistentClient=lambda path: _FakeClient(path=path))  # type: ignore[arg-type]  # noqa: E501
    monkeypatch.setitem(__import__("sys").modules, "chromadb", chroma_mod)

    # Make Azure SDK importable.
    aio_mod = types.ModuleType("azure.search.documents.aio")
    aio_mod.SearchClient = object
    monkeypatch.setitem(
        __import__("sys").modules,
        "azure.search.documents",
        types.ModuleType("azure.search.documents"),
    )
    monkeypatch.setitem(__import__("sys").modules, "azure.search.documents.aio", aio_mod)

    # Patch async search client to succeed (so preflight passes).
    class _DummyClient:
        async def get_document_count(self) -> int:
            return 42

        async def close(self) -> None:
            return None

    monkeypatch.setattr(
        "ingenious.services.azure_search.client_init.make_async_search_client",
        lambda _cfg: _DummyClient(),
    )

    # Provide an AzureSearchProvider that returns a non-empty chunk list.
    class _Provider:
        def __init__(self, _config: Any) -> None:
            return None

        async def retrieve(self, _q: str, *, top_k: int) -> List[Dict[str, Any]]:
            return [
                {
                    "title": "Doc A",
                    "_final_score": 1.0,
                    "snippet": "Alpha",
                    "content": "Bravo",
                }
            ]

        async def close(self) -> None:
            return None

    azure_provider_mod = types.ModuleType(
        "ingenious.services.azure_search.provider"
    )
    setattr(azure_provider_mod, "AzureSearchProvider", _Provider)
    monkeypatch.setitem(
        __import__("sys").modules,
        "ingenious.services.azure_search.provider",
        azure_provider_mod,
    )

    # Force 'use_azure_search' true by making provider appear available.
    monkeypatch.setattr(
        "ingenious.services.chat_services.multi_agent.conversation_flows."
        "knowledge_base_agent.knowledge_base_agent.ConversationFlow._is_azure_search_available",  # noqa: E501
        lambda _self: True,
    )

    # Also allow fallback-on-empty.
    monkeypatch.setenv("KB_FALLBACK_ON_EMPTY", "1")

    # Act.
    text = await flow._search_knowledge_base(
        search_query="q", use_azure_search=True, top_k=3
    )

    # Assert: the Azure-formatted prefix must be present.
    assert text.startswith("Found relevant information from Azure AI Search")
