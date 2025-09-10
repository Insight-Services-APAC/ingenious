# tests/test_streaming/test_flows_kb_local_chroma_edges.py
"""Knowledge Base agent: local Chroma edge cases (no real Chroma required).

Scenarios for `_search_local_chroma()`:
1) Missing KB directory → returns helpful "directory is empty" message (with trailing slash).
2) Chroma not installed → returns install hint.
3) Empty KB directory after initial collection path → returns "No documents found..."
   (achieved by stubbing a minimal `chromadb` module so import succeeds but no docs exist).
"""

from __future__ import annotations

import builtins
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent import knowledge_base_agent as kb_mod


def _stub_parent(cfg: Any) -> Any:
    """Return minimal parent for the flow."""
    return SimpleNamespace(config=cfg, chat_history_repository=None)


@pytest.fixture(autouse=True)
def _patch_memory_manager(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """Provide a no-op memory manager for IConversationFlow init."""
    dummy_mgr = SimpleNamespace(maintain_memory=lambda *a, **k: None)
    monkeypatch.setattr("ingenious.services.memory_manager.get_memory_manager", lambda *_: dummy_mgr)


def _make_cfg(tmp_path: Any) -> Any:
    """Build minimal config with memory path."""
    mem = tmp_path / ".mem"
    mem.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(chat_history=SimpleNamespace(memory_path=str(mem)))


@pytest.mark.anyio
async def test_local_chroma_missing_directory(tmp_path: Any) -> None:
    """When KB directory is absent, method returns actionable 'empty directory' message."""
    flow = kb_mod.ConversationFlow(parent_multi_agent_chat_service=_stub_parent(_make_cfg(tmp_path)))
    # Point to a non-existent KB path
    flow._kb_path = str(tmp_path / "kb_missing")
    flow._chroma_path = str(tmp_path / "chroma")
    msg = await flow._search_local_chroma("q", top_k=3, logger=None)
    expected_path = flow._kb_path + ("" if flow._kb_path.endswith("/") else "/")
    assert msg == f"Error: Knowledge base directory is empty. Please add documents to {expected_path}"


@pytest.mark.anyio
async def test_local_chroma_import_missing_returns_install_hint(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """When `chromadb` import fails, it returns explicit install guidance."""
    flow = kb_mod.ConversationFlow(parent_multi_agent_chat_service=_stub_parent(_make_cfg(tmp_path)))
    kb_dir = tmp_path / "kb_present"
    kb_dir.mkdir(parents=True, exist_ok=True)
    flow._kb_path = str(kb_dir)
    flow._chroma_path = str(tmp_path / "chroma")

    real_import = builtins.__import__

    def _raising_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "chromadb":
            raise ImportError("No module named 'chromadb'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _raising_import)

    msg = await flow._search_local_chroma("q", top_k=3, logger=None)
    assert msg == "Error: ChromaDB not installed. Please install with: uv add chromadb"


@pytest.mark.anyio
async def test_local_chroma_empty_dir_after_collection_creation(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """With stubbed chromadb and empty KB dir, returns 'No documents found...'."""
    flow = kb_mod.ConversationFlow(parent_multi_agent_chat_service=_stub_parent(_make_cfg(tmp_path)))
    kb_dir = tmp_path / "kb_empty"
    kb_dir.mkdir(parents=True, exist_ok=True)
    flow._kb_path = str(kb_dir)
    flow._chroma_path = str(tmp_path / "chroma")

    # Stub a minimal chromadb module to satisfy import but avoid real behavior.
    class _Collection:
        def add(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - not reached for empty docs
            return None

    class _Client:
        def __init__(self, path: str) -> None:  # noqa: ARG002
            return None

        def get_collection(self, name: str) -> Any:  # noqa: ARG002
            raise RuntimeError("not created yet")

        def create_collection(self, name: str) -> _Collection:  # noqa: ARG002
            return _Collection()

    stub = ModuleType("chromadb")
    setattr(stub, "PersistentClient", _Client)
    monkeypatch.setitem(sys.modules, "chromadb", stub)

    msg = await flow._search_local_chroma("q", top_k=3, logger=None)
    assert msg == "Error: No documents found in knowledge base directory"
