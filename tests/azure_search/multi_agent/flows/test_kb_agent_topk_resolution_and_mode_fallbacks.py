"""Test knowledge base agent configuration resolution logic.

This module contains tests to verify that the ConversationFlow for the
knowledge base agent correctly resolves settings like the number of search
results (`top_k`) and the retrieval mode. It specifically tests the
priority order: request parameters override environment variables, which in
turn override hardcoded defaults. It also validates fallback behavior for
invalid or missing configuration values.
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Dict, List

import pytest

import ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent.knowledge_base_agent as kb

if TYPE_CHECKING:
    from pytest import MonkeyPatch


@pytest.mark.asyncio
async def test_request_parameters_string_topk_overrides_env_and_defaults(
    tmp_path: Path,
) -> None:
    """Verify request `kb_top_k` parameter overrides environment and defaults.

    This test ensures that when `kb_top_k` is provided in the request parameters,
    its value is used, even if it's a string, superseding any value from
    environment variables or the hardcoded default.
    """
    flow: kb.ConversationFlow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    flow._config = SimpleNamespace(models=[SimpleNamespace(model="gpt-5")])
    flow._chat_service = None
    flow._memory_path = str(tmp_path)
    # Provide default paths in case of any local fallback path execution
    flow._kb_path = os.path.join(str(tmp_path), "knowledge_base")
    flow._chroma_path = os.path.join(str(tmp_path), "chroma_db")

    class Req:
        """A mock request with a string 'kb_top_k' parameter."""

        user_prompt: str = "q"
        parameters: Dict[str, str] = {"kb_top_k": "12"}

    assert flow._get_top_k("direct", Req()) == 12
    assert flow._get_top_k("assist", Req()) == 12


def test_non_numeric_and_non_positive_topk_values_are_ignored(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """Check that invalid 'kb_top_k' values are ignored and fallbacks are used.

    This test verifies that if the `kb_top_k` parameter in a request is
    non-numeric or non-positive (e.g., "abc" or "0"), it is disregarded.
    The system should then fall back to using the value from the environment
    variable (`KB_TOPK_DIRECT`) or, if that is not set, the default value.
    """
    flow: kb.ConversationFlow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    flow._config = SimpleNamespace(models=[SimpleNamespace(model="gpt-5")])
    flow._chat_service = None
    flow._memory_path = str(tmp_path)
    # Provide default paths in case of any local fallback path execution
    flow._kb_path = os.path.join(str(tmp_path), "knowledge_base")
    flow._chroma_path = os.path.join(str(tmp_path), "chroma_db")

    class BadReq:
        """A mock request with a non-numeric 'kb_top_k' parameter."""

        user_prompt: str = "q"
        parameters: Dict[str, str] = {"kb_top_k": "abc"}  # ignored

    os.environ["KB_TOPK_DIRECT"] = "7"
    assert flow._get_top_k("direct", BadReq()) == 7

    # non-positive should be ignored -> defaults apply when no env set
    monkeypatch.delenv("KB_TOPK_DIRECT", raising=False)

    class ZeroReq:
        """A mock request with a non-positive 'top_k' parameter."""

        user_prompt: str = "q"
        parameters: Dict[str, str] = {"top_k": "0"}

    assert flow._get_top_k("direct", ZeroReq()) == 3  # default


@pytest.mark.asyncio
async def test_invalid_kb_mode_coerces_to_direct(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Ensure an invalid KB_MODE coerces to 'direct' (top_k=3) AND that the Azure path.

    is actually taken (preflight succeeds) so the final response contains the
    'Azure AI Search' prefix.

    Why this test needed a fix:
    ---------------------------
    - The KB flow performs a strict preflight: `await client.get_document_count()`.
    - In this test file we published fake `azure.*` modules into sys.modules (good),
      but we did NOT guarantee that the KB module’s `make_async_search_client` returns
      an instance of THAT fake async client.
    - If a prior patch returns some other fake without `get_document_count`, preflight
      raises, Azure path is skipped, and the flow drops to the Chroma path, causing
      the assertion to fail.

    What we add here:
    -----------------
    - Patch the KB module’s `make_async_search_client` (the **import site** used by the flow)
      to build our fake async SearchClient type that implements `get_document_count()`.
    - Clear policy env vars so nothing forces a local/non-Azure path.
    """
    # 1) Invalid KB_MODE so the flow must coerce to 'direct' (default top_k=3).
    os.environ["KB_MODE"] = "wEiRd"

    # 2) Provider stub that captures the top_k the flow sends to Azure.
    prov_mod = types.ModuleType("ingenious.services.azure_search.provider")
    seen: Dict[str, Any] = {}

    class AzureSearchProvider:
        """Fake Azure provider – records top_k and returns a canned doc."""

        def __init__(self, *a: Any, **k: Any) -> None:
            """Accept whatever constructor args the flow passes."""
            pass

        async def retrieve(self, query: str, top_k: int = 99) -> List[Dict[str, str]]:
            """Record top_k and return one deterministic result."""
            seen["top_k"] = top_k
            return [{"id": "1", "title": "T", "snippet": "S", "content": "C"}]

        async def close(self) -> None:
            """No-op close to match the real provider interface."""
            pass

    prov_mod.AzureSearchProvider = AzureSearchProvider

    # 3) Publish minimal fake Azure SDK modules into sys.modules so imports in the flow
    #    succeed and our preflight can *attempt* to use them.
    import types as _t

    class _Cred:
        """Fake AzureKeyCredential; we only store the key."""

        def __init__(self, k: str) -> None:
            self.k = k

    class _Client:
        """Fake async SearchClient; implements the two async methods the KB preflight needs.

        Methods implemented:
        - get_document_count()
        - close()
        """

        def __init__(self, *, endpoint: str, index_name: str, credential: Any) -> None:
            # Match the real constructor signature for realism; no logic needed here.
            self.endpoint = endpoint
            self.index_name = index_name
            self.credential = credential

        async def get_document_count(self) -> int:
            """Return a positive int so preflight 'passes'."""
            return 1

        async def close(self) -> None:
            """No-op close to match real client surface."""
            pass

    # Install fake 'azure.core.credentials' and 'azure.search.documents.aio'
    monkeypatch.setitem(
        sys.modules, "azure.core.credentials", _t.ModuleType("azure.core.credentials")
    )
    sys.modules["azure.core.credentials"].AzureKeyCredential = _Cred  # type: ignore[attr-defined]

    monkeypatch.setitem(
        sys.modules,
        "azure.search.documents.aio",
        _t.ModuleType("azure.search.documents.aio"),
    )
    sys.modules["azure.search.documents.aio"].SearchClient = _Client  # type: ignore[attr-defined]

    # 4) CRITICAL: Patch the KB module’s *imported* symbol `make_async_search_client` so that
    #    the KB flow actually constructs OUR fake async client above. Patching the factory
    #    module is NOT sufficient because the KB file imported the function by value.
    def _make_fake_client_from_cfg(cfg: Any) -> _Client:
        """Build our fake async client using the stub config the KB preflight passes.

        The stub exposes:
          - search_endpoint
          - search_index_name
          - search_key (str or SecretStr)
        """
        # Unwrap SecretStr if present; tests may pass a plain str
        key_obj = getattr(cfg, "search_key", "")
        if hasattr(key_obj, "get_secret_value"):
            try:
                key = key_obj.get_secret_value()
            except Exception:
                key = ""
        else:
            key = key_obj or ""

        return _Client(
            endpoint=getattr(cfg, "search_endpoint"),
            index_name=getattr(cfg, "search_index_name"),
            credential=_Cred(str(key)),
        )

    # Patch the symbol where it is used by the flow.
    monkeypatch.setattr(kb, "make_async_search_client", _make_fake_client_from_cfg, raising=True)

    # 5) Make sure the Azure provider import is “available” to the flow so
    #    `_is_azure_search_available()` returns True.
    monkeypatch.setitem(sys.modules, "ingenious.services.azure_search.provider", prov_mod)

    # 6) Minimal autogen + LLM factories to satisfy unrelated imports/usage.
    core = _t.ModuleType("autogen_core")
    core.EVENT_LOGGER_NAME = "autogen"

    class CancellationToken:
        """Minimal token class; the flow only needs the symbol to exist."""

        ...

    core.CancellationToken = CancellationToken
    monkeypatch.setitem(sys.modules, "autogen_core", core)
    tools = _t.ModuleType("autogen_core.tools")
    tools.FunctionTool = object  # not exercised in this test path
    monkeypatch.setitem(sys.modules, "autogen_core.tools", tools)
    ag = _t.ModuleType("autogen_agentchat.agents")
    ag.AssistantAgent = object  # not exercised in this test path
    monkeypatch.setitem(sys.modules, "autogen_agentchat.agents", ag)

    class DummyLLMClient:
        """Tiny async LLM client with a no-op close() to satisfy flow cleanup."""

        async def close(self) -> None:
            pass

    # The flow constructs a chat completion client; return our dummy async client.
    monkeypatch.setattr(
        kb,
        "AzureClientFactory",
        SimpleNamespace(create_openai_chat_completion_client=lambda _cfg: DummyLLMClient()),
        raising=False,
    )

    # 7) Defensive: clear any policy env that might force local/Chroma.
    #    The default policy in the flow is 'azure_only'; we want to exercise Azure, not local.
    monkeypatch.delenv("KB_POLICY", raising=False)
    monkeypatch.delenv("KB_FALLBACK_ON_EMPTY", raising=False)

    # 8) Build a flow instance with a minimal, valid Azure service configuration.
    flow: kb.ConversationFlow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    flow._config = SimpleNamespace(
        models=[SimpleNamespace(model="gpt-5")],
        azure_search_services=[SimpleNamespace(endpoint="https://s", key="k", index_name="idx")],
    )
    flow._chat_service = None
    flow._memory_path = str(tmp_path)

    # Provide default local paths just in case logging touches them (not used here).
    flow._kb_path = os.path.join(str(tmp_path), "knowledge_base")
    flow._chroma_path = os.path.join(str(tmp_path), "chroma_db")

    # 9) Execute the code under test with a real ChatRequest.
    from ingenious.models.chat import ChatRequest

    resp = await flow.get_conversation_response(ChatRequest(user_prompt="q"))

    # 10) Assertions: Azure path used, and 'direct' default top_k=3 was applied.
    assert "Found relevant information from Azure AI Search" in resp.agent_response
    assert seen.get("top_k") == 3
