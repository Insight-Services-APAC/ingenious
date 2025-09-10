# tests/test_streaming/test_flows_kb_preflight_and_policy.py
"""Knowledge Base agent: Azure preflight & policy/top‑k plumbing (unit level).

Covers:
A) `_require_valid_azure_index` split phases:
   - not_configured (sync raise),
   - incomplete_config (sync raise),
   - sdk_missing (awaitable raise when SDK import fails).
B) `_should_use_azure_search` policy gate behavior.
C) Top‑k resolution via `_resolve_topk_from_request` and `_get_top_k`.
D) `_ensure_default_azure_index` environment defaulting and fallback.

All tests avoid network and real Azure SDK by monkeypatching minimal seams.
"""

from __future__ import annotations

import os
import sys
from types import ModuleType, SimpleNamespace
from typing import Any, Optional

import pytest

from ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent import knowledge_base_agent as kb_mod
from ingenious.services.retrieval.errors import PreflightError


def _stub_parent(cfg: Any) -> Any:
    """Return a minimal parent service stub required by IConversationFlow."""
    return SimpleNamespace(config=cfg, chat_history_repository=None)


@pytest.fixture(autouse=True)
def _patch_memory_manager(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """Provide a no-op memory manager and a minimal config shape for IConversationFlow."""
    dummy_mgr = SimpleNamespace(maintain_memory=lambda *a, **k: None)
    monkeypatch.setattr("ingenious.services.memory_manager.get_memory_manager", lambda *_: dummy_mgr)


def _make_cfg(
    tmp_path: Any,
    azure_services: Optional[list[Any]] = None,
) -> Any:
    """Build a minimal config object with memory path and optional Azure services."""
    memory_root = tmp_path / ".mem"
    memory_root.mkdir(parents=True, exist_ok=True)
    chat_history = SimpleNamespace(memory_path=str(memory_root))
    cfg = SimpleNamespace(chat_history=chat_history)
    if azure_services is not None:
        cfg.azure_search_services = azure_services
    return cfg


def test_require_valid_azure_index_not_configured_sync(tmp_path: Any) -> None:
    """No service configured → raises PreflightError('not_configured') synchronously."""
    flow = kb_mod.ConversationFlow(parent_multi_agent_chat_service=_stub_parent(_make_cfg(tmp_path)))
    with pytest.raises(PreflightError) as exc:
        _ = flow._require_valid_azure_index()
    assert exc.value.reason == "not_configured"


def test_require_valid_azure_index_incomplete_config_sync(tmp_path: Any) -> None:
    """Service present but missing endpoint/key/index → raises 'incomplete_config' synchronously."""
    svc = SimpleNamespace(endpoint="", key="", index_name="")
    cfg = _make_cfg(tmp_path, azure_services=[svc])
    flow = kb_mod.ConversationFlow(parent_multi_agent_chat_service=_stub_parent(cfg))
    with pytest.raises(PreflightError) as exc:
        _ = flow._require_valid_azure_index()
    assert exc.value.reason == "incomplete_config"


@pytest.mark.anyio
async def test_require_valid_azure_index_sdk_missing_async(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """Valid config but SDK import missing → awaitable raises 'sdk_missing'."""
    svc = SimpleNamespace(endpoint="https://example", key="real-key", index_name="idx")
    cfg = _make_cfg(tmp_path, azure_services=[svc])
    flow = kb_mod.ConversationFlow(parent_multi_agent_chat_service=_stub_parent(cfg))

    # Create empty modules for azure.* chain lacking 'SearchClient' -> ImportError
    for name in (
        "azure",
        "azure.search",
        "azure.search.documents",
        "azure.search.documents.aio",
    ):
        mod = ModuleType(name)
        monkeypatch.setitem(sys.modules, name, mod)

    awaitable = flow._require_valid_azure_index()
    with pytest.raises(PreflightError) as exc:
        await awaitable
    assert exc.value.reason == "sdk_missing"


def test_should_use_azure_search_policy_gate(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """Policy gate returns False with no service or mock key, True when available."""
    # No service configured
    flow = kb_mod.ConversationFlow(parent_multi_agent_chat_service=_stub_parent(_make_cfg(tmp_path)))
    assert flow._should_use_azure_search() is False

    # Mock key forces False
    svc = SimpleNamespace(endpoint="https://example", key="mock-search-key-12345", index_name="")
    flow2 = kb_mod.ConversationFlow(parent_multi_agent_chat_service=_stub_parent(_make_cfg(tmp_path, [svc])))
    assert flow2._should_use_azure_search() is False

    # Endpoint + real key + available SDK (we monkeypatch availability method)
    svc2 = SimpleNamespace(endpoint="https://example", key="real", index_name="")
    flow3 = kb_mod.ConversationFlow(parent_multi_agent_chat_service=_stub_parent(_make_cfg(tmp_path, [svc2])))
    monkeypatch.setattr(flow3, "_is_azure_search_available", lambda: True)
    assert flow3._should_use_azure_search() is True


def test_resolve_topk_from_request_direct_attrs_and_params(tmp_path: Any) -> None:
    """Resolution checks kb_top_k > top_k > search_top_k; supports string digits and parameters dict."""
    flow = kb_mod.ConversationFlow(parent_multi_agent_chat_service=_stub_parent(_make_cfg(tmp_path)))

    req1 = SimpleNamespace(kb_top_k=7)
    assert flow._resolve_topk_from_request(req1) == 7

    req2 = SimpleNamespace(top_k="5")
    assert flow._resolve_topk_from_request(req2) == 5

    req3 = SimpleNamespace(search_top_k="7")
    assert flow._resolve_topk_from_request(req3) == 7

    req4 = SimpleNamespace(parameters={"top_k": "8"})
    assert flow._resolve_topk_from_request(req4) == 8


def test_get_top_k_request_override_then_env_then_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """Request override wins; otherwise env wins; otherwise defaults per mode."""
    flow = kb_mod.ConversationFlow(parent_multi_agent_chat_service=_stub_parent(_make_cfg(tmp_path)))

    # Env overrides
    monkeypatch.setenv("KB_TOPK_ASSIST", "9")
    monkeypatch.setenv("KB_TOPK_DIRECT", "6")

    # Assist: env wins when no request override
    assert flow._get_top_k("assist", chat_request=None) == 9
    # Direct: env wins when no request override
    assert flow._get_top_k("direct", chat_request=None) == 6

    # Request override via parameters takes precedence
    req = SimpleNamespace(parameters={"kb_top_k": "4"})
    assert flow._get_top_k("assist", chat_request=req) == 4
    assert flow._get_top_k("direct", chat_request=req) == 4

    # Clear env for defaults
    monkeypatch.delenv("KB_TOPK_ASSIST", raising=False)
    monkeypatch.delenv("KB_TOPK_DIRECT", raising=False)
    assert flow._get_top_k("assist", chat_request=None) == kb_mod._TOPK_ASSIST_DEFAULT
    assert flow._get_top_k("direct", chat_request=None) == kb_mod._TOPK_DIRECT_DEFAULT


def test_ensure_default_azure_index_env_and_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """When index absent: use env AZURE_SEARCH_DEFAULT_INDEX or fallback to 'test-index'."""
    svc = SimpleNamespace(endpoint="https://e", key="k", index_name="")
    cfg = _make_cfg(tmp_path, azure_services=[svc])
    flow = kb_mod.ConversationFlow(parent_multi_agent_chat_service=_stub_parent(cfg))

    # Env default
    monkeypatch.setenv("AZURE_SEARCH_DEFAULT_INDEX", "env-default")
    flow._ensure_default_azure_index()
    assert svc.index_name == "env-default"

    # Fallback default when env missing
    svc2 = SimpleNamespace(endpoint="https://e", key="k", index_name="")
    cfg2 = _make_cfg(tmp_path, azure_services=[svc2])
    flow2 = kb_mod.ConversationFlow(parent_multi_agent_chat_service=_stub_parent(cfg2))
    monkeypatch.delenv("AZURE_SEARCH_DEFAULT_INDEX", raising=False)
    flow2._ensure_default_azure_index()
    assert svc2.index_name == "test-index"
