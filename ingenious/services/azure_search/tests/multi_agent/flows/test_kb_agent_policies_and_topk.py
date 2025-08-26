"""Policy/top‑k resolution tests for KB Agent (non‑streaming direct mode).

This module contains two direct‑mode tests that verify: (1) `prefer_azure`
with fallback disabled returns a clear "no information found" message when
Azure returns nothing, and (2) invalid `KB_MODE` coerces to `direct`, which
ignores env top_k overrides but still honors per‑request overrides.

Key entry points:
- ConversationFlow._search_knowledge_base (internal) and
- ConversationFlow.get_conversation_response (public, non‑streaming).

I/O/deps/side effects:
- No network. Patches:
  * ConversationFlow._is_azure_search_available → True
  * ConversationFlow._preflight_azure_index_async → no‑op
  * ingenious.services.azure_search.provider.AzureSearchProvider → stubs
  * AzureClientFactory.create_openai_chat_completion_client → stub

Usage:
- Run with `pytest -q`.
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

_KB_MOD_PATH: str = (
    "ingenious.services.chat_services.multi_agent.conversation_flows."
    "knowledge_base_agent.knowledge_base_agent"
)


def _make_flow(tmp_path: Any) -> Any:
    """Create a minimally initialized ConversationFlow instance for tests.

    Args:
        tmp_path: Pytest temporary directory.

    Returns:
        A ConversationFlow with config and KB/chroma paths set.
    """
    kb_mod = importlib.import_module(_KB_MOD_PATH)
    flow = object.__new__(kb_mod.ConversationFlow)

    config = SimpleNamespace(
        models=[SimpleNamespace(model="gpt-4o")],
        azure_search_services=[
            SimpleNamespace(
                endpoint="https://search.example.net",
                index_name="idx",
                key="sk",
            )
        ],
        knowledge_base_mode=None,
        knowledge_base_policy=None,
    )

    flow._config = config
    flow._chat_service = None
    flow._kb_path = str(tmp_path / "kb")
    flow._chroma_path = str(tmp_path / "chroma")
    flow._last_mem_warn_ts = 0.0
    return flow


class _SpyProviderEmpty:
    """AzureSearchProvider stub that returns an empty result set."""

    def __init__(self, *_: Any, **__: Any) -> None:
        """Initialize the stub provider (no state required)."""
        return None

    async def retrieve(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """Return an empty list to simulate 'no hits' from Azure."""
        return []

    async def close(self) -> None:
        """Provide an awaitable close method for lifecycle parity."""
        return None


class _SpyProviderCapture:
    """AzureSearchProvider stub that captures the `top_k` argument."""

    calls: list[tuple[str, int]] = []

    def __init__(self, *_: Any, **__: Any) -> None:
        """Initialize the capture stub."""
        return None

    async def retrieve(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """Record (query, top_k) and return a trivial non-empty payload."""
        _SpyProviderCapture.calls.append((query, top_k))
        return [{"id": "1", "content": "ok", "_final_score": 1.0}]

    async def close(self) -> None:
        """Provide an awaitable close method."""
        return None


class _StubModelClient:
    """Async model client stub that only needs a close()."""

    async def close(self) -> None:
        """Provide an awaitable close method for the agent lifecycle."""
        return None


@pytest.mark.asyncio
async def test_prefer_azure_no_fallback_returns_no_info_when_empty(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert `prefer_azure` with fallback disabled returns an Azure 'no info' message.

    When KB_POLICY=prefer_azure and KB_FALLBACK_ON_EMPTY is unset/false, empty
    Azure results should not fall back to local; the agent should report that
    Azure had no relevant information.
    """
    kb_mod = importlib.import_module(_KB_MOD_PATH)
    flow = _make_flow(tmp_path)

    # Policy + availability setup.
    monkeypatch.setenv("KB_POLICY", "prefer_azure")
    monkeypatch.delenv("KB_FALLBACK_ON_EMPTY", raising=False)
    monkeypatch.setattr(
        kb_mod.ConversationFlow, "_is_azure_search_available", lambda _self: True
    )
    monkeypatch.setattr(
        kb_mod.ConversationFlow,
        "_preflight_azure_index_async",
        AsyncMock(return_value=None),
    )

    # Patch provider to return no results and stub the model client.
    with (
        patch(
            "ingenious.services.azure_search.provider.AzureSearchProvider",
            new=_SpyProviderEmpty,
        ),
        patch.object(
            kb_mod.AzureClientFactory,
            "create_openai_chat_completion_client",
            return_value=_StubModelClient(),
        ),
    ):
        text: str = await flow._search_knowledge_base(
            search_query="When is X?",
            use_azure_search=True,
            top_k=3,
            logger=None,
        )

    assert text.startswith("No relevant information found in Azure AI Search"), (
        f"Unexpected response: {text!r}"
    )


@pytest.mark.asyncio
async def test_coerced_mode_direct_ignores_env_but_honors_request_topk(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert invalid `KB_MODE` coerces to `direct` and uses request `kb_top_k`.

    With an invalid KB_MODE, the agent coerces to 'direct' and ignores env top_k
    overrides, but it still honors per-request overrides. We verify the provider
    receives the request-level `top_k`.
    """
    kb_mod = importlib.import_module(_KB_MOD_PATH)
    flow = _make_flow(tmp_path)

    # Force invalid mode → coerced 'direct'; set env top_k which should be ignored.
    monkeypatch.setenv("KB_MODE", "weird")
    monkeypatch.setenv("KB_TOPK_DIRECT", "99")

    # Ensure Azure path is taken and preflight passes.
    monkeypatch.setattr(
        kb_mod.ConversationFlow, "_is_azure_search_available", lambda _self: True
    )
    monkeypatch.setattr(
        kb_mod.ConversationFlow,
        "_preflight_azure_index_async",
        AsyncMock(return_value=None),
    )

    # Provider spy + model client stub.
    _SpyProviderCapture.calls = []
    with (
        patch(
            "ingenious.services.azure_search.provider.AzureSearchProvider",
            new=_SpyProviderCapture,
        ),
        patch.object(
            kb_mod.AzureClientFactory,
            "create_openai_chat_completion_client",
            return_value=_StubModelClient(),
        ),
    ):
        from ingenious.models.chat import ChatRequest

        req = ChatRequest(user_prompt="State the Azure summary.")
        if hasattr(req, "parameters") and isinstance(req.parameters, dict):
            req.parameters["kb_top_k"] = 5
        else:
            setattr(req, "parameters", {"kb_top_k": 5})

        # Call the public non-streaming entry point (direct mode).
        _ = await flow.get_conversation_response(req)

    # Verify provider captured the request-level top_k=5 (not env 99).
    assert _SpyProviderCapture.calls, "Expected the provider to be called once."
    _, seen_topk = _SpyProviderCapture.calls[0]
    assert seen_topk == 5, f"expected top_k=5 to be honored, got {seen_topk}"
