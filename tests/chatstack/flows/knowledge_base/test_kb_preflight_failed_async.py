"""Azure KB preflight: network failure → PreflightError('preflight_failed').

Covers the async preflight branch in knowledge_base_agent to ensure SDK import
succeeds but `get_document_count()` fails with a network/403-like error, which
must be surfaced as `reason == "preflight_failed"` with a masked snapshot.
"""

from __future__ import annotations

import types
from typing import Any

import pytest

from ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent.knowledge_base_agent import (  # noqa: E501
    ConversationFlow,
)
from ingenious.services.retrieval.errors import PreflightError


@pytest.mark.asyncio
async def test_kb_preflight_azure_index_preflight_failed_async(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """Raise 'preflight_failed' when get_document_count() fails."""
    # Patch the memory manager to avoid external side effects.
    monkeypatch.setattr(
        "ingenious.services.chat_services.multi_agent.service.get_memory_manager",
        lambda _cfg, _path: types.SimpleNamespace(
            maintain_memory=lambda *_a, **_k: None
        ),
    )

    # Provide a minimal parent with Azure Search config.
    class _AzureSvc:
        endpoint = "https://example.search.windows.net"
        index_name = "idx"
        key = "abc123"

    class _Cfg:
        def __init__(self, root: str) -> None:
            self.chat_history = types.SimpleNamespace(memory_path=root)
            self.models = [types.SimpleNamespace(model="stub")]
            self.azure_search_services = [_AzureSvc()]

    class _Parent:
        def __init__(self, cfg: Any) -> None:
            self.config = cfg

    cfg = _Cfg(str(tmp_path))
    flow = ConversationFlow(parent_multi_agent_chat_service=_Parent(cfg))

    # Patch Azure SDK import so it exists.
    aio_mod = types.ModuleType("azure.search.documents.aio")
    aio_mod.SearchClient = object  # sentinel type
    monkeypatch.setitem(
        __import__("sys").modules,
        "azure.search.documents",
        types.ModuleType("azure.search.documents"),
    )
    monkeypatch.setitem(__import__("sys").modules, "azure.search.documents.aio", aio_mod)

    # Patch the async client factory to return a dummy that fails on count.
    class _DummyClient:
        async def get_document_count(self) -> int:
            raise Exception("403 Forbidden")

        async def close(self) -> None:
            return None

    monkeypatch.setattr(
        "ingenious.services.azure_search.client_init.make_async_search_client",
        lambda _cfg: _DummyClient(),
    )

    # Act & Assert.
    with pytest.raises(PreflightError) as exc:
        await flow._preflight_azure_index_async(
            endpoint=_AzureSvc.endpoint,
            index_name=_AzureSvc.index_name,
            key_val=_AzureSvc.key,
        )
    assert exc.value.reason == "preflight_failed"
    snap = exc.value.snapshot or {}
    assert "kb_service_key_masked" in snap
    assert "env_AZURE_SEARCH_KEY_masked" in snap
