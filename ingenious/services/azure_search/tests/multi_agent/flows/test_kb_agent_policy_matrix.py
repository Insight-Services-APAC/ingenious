"""Test the knowledge base agent's policy matrix for search providers.

This module contains tests for the `_search_knowledge_base` method within the
`ConversationFlow` for the knowledge base agent. It specifically validates the
behavior of the search provider selection logic, which is governed by the
`KB_POLICY` and `KB_FALLBACK_ON_EMPTY` environment variables. The tests ensure
that the flow correctly chooses between Azure AI Search and a local ChromaDB
instance based on the configured policy (e.g., 'prefer_azure', 'prefer_local')
and handles fallbacks when the primary provider returns no results.
"""

from __future__ import annotations

import logging
import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Coroutine, Dict, Generator, List, Type

import pytest

import ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent.knowledge_base_agent as kb
from ingenious.services.retrieval.errors import PreflightError

if TYPE_CHECKING:
    from _pytest.logging import LogCaptureFixture
    from pytest import MonkeyPatch


# ──────────────────────────────────────────────────────────────────────────────
# Small test doubles and helpers
# ──────────────────────────────────────────────────────────────────────────────


class AcceptingLogHandler(logging.Handler):
    """A logging handler that does nothing, used to silence log output."""

    def emit(self, record: logging.LogRecord) -> None:
        """Accept and discard any log record."""
        pass


class DummyLLMClient:
    """A fake LLM client that provides a no-op close method for tests."""

    async def close(self) -> None:
        """Simulate closing the client connection."""
        pass


def install_minimal_autogen(monkeypatch: MonkeyPatch) -> None:
    """Install minimal, fake autogen modules to satisfy imports.

    This avoids needing the full autogen library for these tests, patching
    `sys.modules` with just enough structure to allow the agent code to load.
    """
    core_mod = types.ModuleType("autogen_core")
    core_mod.EVENT_LOGGER_NAME = "autogen"

    class _CT: ...

    core_mod.CancellationToken = _CT
    monkeypatch.setitem(sys.modules, "autogen_core", core_mod)

    tools_mod = types.ModuleType("autogen_core.tools")

    class _FT: ...

    tools_mod.FunctionTool = _FT
    monkeypatch.setitem(sys.modules, "autogen_core.tools", tools_mod)

    agents_mod = types.ModuleType("autogen_agentchat.agents")

    class _Assistant: ...

    agents_mod.AssistantAgent = _Assistant
    monkeypatch.setitem(sys.modules, "autogen_agentchat.agents", agents_mod)

    msgs_mod = types.ModuleType("autogen_agentchat.messages")

    class TextMessage:
        def __init__(self, content: str, source: str) -> None:
            self.content = content
            self.source = source

    monkeypatch.setitem(sys.modules, "autogen_agentchat.messages", msgs_mod)


def install_memory_manager(monkeypatch: MonkeyPatch) -> None:
    """Install a fake memory manager module.

    This provides dummy implementations of the memory manager functions to
    isolate the tests from the actual memory management logic.
    """
    mm = types.ModuleType("ingenious.services.memory_manager")

    class _MM:
        async def close(self) -> None:
            pass

        async def maintain_memory(self, new_content: str, max_words: int) -> None:
            return None

    def get_memory_manager(config: Any, path: str) -> _MM:
        return _MM()

    async def run_async_memory_operation(coro: Coroutine[Any, Any, Any]) -> Any:
        return await coro

    mm.get_memory_manager = get_memory_manager
    mm.run_async_memory_operation = run_async_memory_operation
    monkeypatch.setitem(sys.modules, "ingenious.services.memory_manager", mm)


def make_config(
    *,
    endpoint: str = "https://x.search.windows.net",
    key: str = "real-key",
    index_name: str = "idx",
) -> SimpleNamespace:
    """Create a mock configuration object for the conversation flow.

    This helper generates a `SimpleNamespace` that mimics the structure of the
    real application configuration, providing necessary details for Azure Search.
    """
    cfg = SimpleNamespace()
    cfg.models = [SimpleNamespace(model="gpt-4o")]
    cfg.azure_search_services = [
        SimpleNamespace(
            endpoint=endpoint,
            key=key,
            index_name=index_name,
            use_semantic_ranking=False,
            semantic_ranking=False,
            semantic_configuration=None,
            top_k_retrieval=20,
            top_n_final=5,
            id_field="id",
            content_field="content",
            vector_field="vector",
        )
    ]
    return cfg


def install_azure_sdk_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Install a minimal, in-process *fake* Azure SDK and ensure the KB module
    builds its SearchClient from that fake.

    Why:
    ----
    The KB agent's preflight does a strict health check:
        await client.get_document_count()
    In tests we don't want real cloud calls, so we publish tiny fake modules
    into sys.modules that simulate just enough of the Azure SDK surface:
      * azure.core.credentials.AzureKeyCredential
      * azure.search.documents.aio.SearchClient
          - async get_document_count()
          - async close()
    Finally, we patch the central seam
    'ingenious.services.azure_search.client_init.make_async_search_client' to
    return our fake client, guaranteeing preflight sees a client with the
    expected methods.
    """

    import sys
    import types

    # -----------------------------
    # 1) Minimal fake SDK classes
    # -----------------------------

    class _FakeAzureKeyCredential:
        """
        Fake replacement for azure.core.credentials.AzureKeyCredential.
        We only store the key for realism; no real auth happens in tests.
        """

        def __init__(self, key: str) -> None:
            self.key = key

    class _FakeAsyncSearchClient:
        """
        Fake replacement for azure.search.documents.aio.SearchClient with the
        two async methods our KB preflight actually calls.
        """

        def __init__(self, *, endpoint: str, index_name: str, credential: Any) -> None:
            self.endpoint = endpoint
            self.index_name = index_name
            self.credential = credential
            self._closed = False

        async def get_document_count(self) -> int:
            """
            Simulate a successful health check. If you need to simulate failures
            (e.g., 401/timeout) in other tests, you can modify this to raise.
            """
            return 1

        async def close(self) -> None:
            """Simulate the real client's async close()."""
            self._closed = True

    # ---------------------------------------------------
    # 2) Publish fake azure.* modules into sys.modules
    #    so 'import azure....' resolves to our fakes.
    # ---------------------------------------------------

    fake_credentials_mod = types.ModuleType("azure.core.credentials")
    setattr(fake_credentials_mod, "AzureKeyCredential", _FakeAzureKeyCredential)

    fake_aio_mod = types.ModuleType("azure.search.documents.aio")
    setattr(fake_aio_mod, "SearchClient", _FakeAsyncSearchClient)

    monkeypatch.setitem(sys.modules, "azure.core.credentials", fake_credentials_mod)
    monkeypatch.setitem(sys.modules, "azure.search.documents.aio", fake_aio_mod)

    # -----------------------------------------------------------------
    # 3) Patch the symbol where it is USED (the KB module), not the
    #    original factory. The KB file did:
    #       from ingenious.services.azure_search.client_init import make_async_search_client
    #    so we must patch kb.make_async_search_client directly.
    # -----------------------------------------------------------------

    def _build_fake_client_from_cfg(cfg: Any) -> _FakeAsyncSearchClient:
        """
        KB preflight passes a SimpleNamespace with:
          - search_endpoint
          - search_index_name
          - search_key (string or SecretStr)
        We unwrap SecretStr if present and return our fake async client.
        """
        endpoint = getattr(cfg, "search_endpoint")
        index_name = getattr(cfg, "search_index_name")

        key_obj = getattr(cfg, "search_key", "")
        if hasattr(key_obj, "get_secret_value"):
            try:
                key = key_obj.get_secret_value()
            except Exception:
                key = ""
        else:
            key = key_obj or ""

        return _FakeAsyncSearchClient(
            endpoint=endpoint,
            index_name=index_name,
            credential=_FakeAzureKeyCredential(key),
        )

    # This ensures preflight builds a client with async get_document_count() + close().
    monkeypatch.setattr(
        "ingenious.services.azure_search.client_init.make_async_search_client",
        _build_fake_client_from_cfg,
        raising=True,
    )

    # -----------------------------------------------------------------
    # 4) (Optional) Reset any cached factory singleton to avoid stale
    #    state when tests run in different orders. Safe to ignore errors.
    # -----------------------------------------------------------------
    try:
        monkeypatch.setattr(
            "ingenious.services.azure_search.client_init._FACTORY_SINGLETON",
            None,
            raising=False,
        )
    except Exception:
        pass

def install_fake_provider(
    monkeypatch: MonkeyPatch, results: list[dict[str, Any]] | None = None
) -> tuple[list[dict[str, Any]], Type[Any]]:
    """Install a fake AzureSearchProvider that records calls and returns canned results."""
    calls: List[Dict[str, Any]] = []
    prov_mod = types.ModuleType("ingenious.services.azure_search.provider")

    class AzureSearchProvider:
        created = 0

        def __init__(self, *_: Any) -> None:
            AzureSearchProvider.created += 1

        async def retrieve(
            self, query: str, top_k: int = 10, **_: Any
        ) -> list[dict[str, Any]]:
            calls.append({"query": query, "top_k": top_k})
            return list(results or [])

        async def close(self) -> None:
            pass

    prov_mod.AzureSearchProvider = AzureSearchProvider
    monkeypatch.setitem(
        sys.modules, "ingenious.services.azure_search.provider", prov_mod
    )
    return calls, AzureSearchProvider


def install_fake_chromadb(
    monkeypatch: MonkeyPatch, docs: list[str] | None = None, query_empty: bool = False
) -> None:
    """Install a fake ChromaDB client for testing local knowledge base access.

    This mock simulates ChromaDB's client and collection objects, allowing control
    over query results for testing fallback policies.
    """
    chroma = types.ModuleType("chromadb")

    class _Coll:
        def add(self, documents: Any, ids: Any) -> None:
            pass

        def query(self, query_texts: Any, n_results: Any) -> dict[str, list[list[str]]]:
            if query_empty:
                return {"documents": [[]]}
            return {"documents": [[(docs or ["C1", "C2"])[0]]]}

    class _Cli:
        def __init__(self, path: str) -> None:
            self.path = path

        def get_collection(self, name: str) -> _Coll:
            return _Coll()

        def create_collection(self, name: str) -> _Coll:
            return _Coll()

    chroma.PersistentClient = _Cli
    monkeypatch.setitem(sys.modules, "chromadb", chroma)


# ──────────────────────────────────────────────────────────────────────────────
# Autouse: keep environment clean and basic patches in place
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _common(monkeypatch: MonkeyPatch) -> Generator[None, None, None]:
    """Set up common test conditions for all tests in this module.

    This fixture automatically applies essential patches for every test:
    - Fakes autogen and memory manager to remove external dependencies.
    - Silences LLM usage tracking.
    - Fakes the LLM client creation.
    - Cleans up relevant environment variables before each test.
    """
    install_minimal_autogen(monkeypatch)
    install_memory_manager(monkeypatch)
    monkeypatch.setattr(kb, "LLMUsageTracker", AcceptingLogHandler, raising=False)
    monkeypatch.setattr(kb, "LLMUsageTracker", AcceptingLogHandler, raising=False)
    # Patch new client factory
    monkeypatch.setattr(
        kb,
        "AzureClientFactory",
        SimpleNamespace(
            create_openai_chat_completion_client=lambda _cfg: DummyLLMClient()
        ),
    )
    for var in (
        "KB_POLICY",
        "KB_FALLBACK_ON_EMPTY",
        "AZURE_SEARCH_DEFAULT_INDEX",
        "KB_AZURE_SNIPPET_CAP",
    ):
        monkeypatch.delenv(var, raising=False)
    yield


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_policy_azure_only_without_azure_raises_policy_error(
    tmp_path: Path,
) -> None:
    """Verify that using Azure-only policy without Azure configured raises a PreflightError.

    This test ensures that if the policy is set to only use Azure Search, but the
    `use_azure_search` flag is False (e.g., due to missing config), a policy-related
    error is raised, preventing the flow from proceeding with a misconfiguration.
    """
    # ensure local KB exists so Chroma path is usable
    kb_dir = os.path.join(str(tmp_path), "knowledge_base")
    os.makedirs(kb_dir, exist_ok=True)

    flow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    flow._config = make_config()
    flow._chat_service = None
    flow._memory_path = str(tmp_path)
    flow._kb_path = kb_dir
    flow._chroma_path = os.path.join(str(tmp_path), "chroma_db")
    with pytest.raises(PreflightError) as ei:
        await flow._search_knowledge_base(
            search_query="q",
            use_azure_search=False,  # gate closed
            top_k=3,
            logger=logging.getLogger("test"),
        )
    assert ei.value.reason == "policy"


@pytest.mark.asyncio
async def test_prefer_azure_fallback_on_empty_switches_to_chroma(
    tmp_path: Path, monkeypatch: MonkeyPatch, caplog: LogCaptureFixture
) -> None:
    """Test that 'prefer_azure' policy falls back to ChromaDB when Azure returns empty results."""
    # Azure preflight OK but returns NO results -> fallback to Chroma (KB_FALLBACK_ON_EMPTY=1)
    install_azure_sdk_ok(monkeypatch)
    calls, _Prov = install_fake_provider(monkeypatch, results=[])  # empty results
    install_fake_chromadb(monkeypatch, docs=["LocalDoc"])
    os.environ["KB_POLICY"] = "prefer_azure"
    os.environ["KB_FALLBACK_ON_EMPTY"] = "1"

    # ensure local KB exists so Chroma path is usable
    kb_dir: str = os.path.join(str(tmp_path), "knowledge_base")
    os.makedirs(kb_dir, exist_ok=True)

    flow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    flow._config = make_config()
    flow._chat_service = None
    flow._memory_path = str(tmp_path)
    flow._kb_path = kb_dir
    flow._chroma_path = os.path.join(str(tmp_path), "chroma_db")

    caplog.set_level(logging.WARNING)
    out: str = await flow._search_knowledge_base(
        "alpha", use_azure_search=True, top_k=3, logger=logging.getLogger("t")
    )
    # Warning and local fallback
    assert any(
        "falling back to ChromaDB" in (r.getMessage() or "") for r in caplog.records
    )
    assert "Found relevant information from ChromaDB:" in out
    assert len(calls) == 1  # Azure was attempted once


@pytest.mark.asyncio
async def test_prefer_local_uses_local_without_azure_instantiation(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Verify that 'prefer_local' policy uses ChromaDB and does not instantiate the Azure provider."""
    # Chroma returns a doc; Azure provider MUST NOT be instantiated
    install_fake_chromadb(monkeypatch, docs=["LocalDoc"])
    calls, ProviderClass = install_fake_provider(
        monkeypatch, results=[{"id": "x"}]
    )  # should remain unused

    os.environ["KB_POLICY"] = "prefer_local"

    kb_dir = os.path.join(str(tmp_path), "knowledge_base")
    os.makedirs(kb_dir, exist_ok=True)

    flow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    flow._config = make_config()
    flow._chat_service = None
    flow._memory_path = str(tmp_path)
    flow._kb_path = kb_dir
    flow._chroma_path = os.path.join(str(tmp_path), "chroma_db")

    out: str = await flow._search_knowledge_base(
        "q", use_azure_search=True, top_k=3, logger=None
    )
    assert "Found relevant information from ChromaDB:" in out
    assert ProviderClass.created == 0  # no instantiation
    assert calls == []


@pytest.mark.asyncio
async def test_prefer_local_empty_then_fallback_on_empty_calls_azure(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Test 'prefer_local' falls back to Azure if local search is empty and fallback is enabled."""
    # Local returns "No relevant information ..." -> with KB_FALLBACK_ON_EMPTY=1, Azure should be invoked
    install_azure_sdk_ok(monkeypatch)
    calls, ProviderClass = install_fake_provider(
        monkeypatch, results=[{"id": "1", "title": "T", "snippet": "S", "content": "C"}]
    )
    install_fake_chromadb(monkeypatch, query_empty=True)

    os.environ["KB_POLICY"] = "prefer_local"
    os.environ["KB_FALLBACK_ON_EMPTY"] = "1"

    kb_dir = os.path.join(str(tmp_path), "knowledge_base")
    os.makedirs(kb_dir, exist_ok=True)

    flow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    flow._config = make_config()
    flow._chat_service = None
    flow._memory_path = str(tmp_path)
    flow._kb_path = kb_dir
    flow._chroma_path = os.path.join(str(tmp_path), "chroma_db")
    out: str = await flow._search_knowledge_base(
        "what", use_azure_search=True, top_k=5, logger=None
    )
    assert ProviderClass.created == 1
    assert len(calls) == 1
    assert "Found relevant information from Azure AI Search:" in out


def test_should_use_azure_search_rejects_mock_key_and_missing_sdk(
    monkeypatch: MonkeyPatch,
) -> None:
    """Verify the pre-check for using Azure Search correctly handles mock keys and SDK availability."""
    flow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    flow._config = make_config(key="mock-search-key-12345")
    flow._chat_service = None
    flow._memory_path = "."

    # Provider importable reported as True; but mock key blocks
    monkeypatch.setattr(
        kb.ConversationFlow, "_is_azure_search_available", lambda self: True
    )
    assert flow._should_use_azure_search() is False

    # Real key but provider unavailable -> False
    flow._config = make_config(key="real", index_name="idx")
    monkeypatch.setattr(
        kb.ConversationFlow, "_is_azure_search_available", lambda self: False
    )
    assert flow._should_use_azure_search() is False

    # Real key + provider importable -> True
    monkeypatch.setattr(
        kb.ConversationFlow, "_is_azure_search_available", lambda self: True
    )
    assert flow._should_use_azure_search() is True
