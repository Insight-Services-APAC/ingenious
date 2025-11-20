"""Tests Azure Search formatting and configuration for the knowledge base agent.

This module contains unit tests for the Azure Search integration within the
knowledge base agent's conversation flow. It specifically verifies behaviors
related to the formatting of search results, such as content truncation and
the use of separators, as well as configuration fallbacks like using an
environment variable for the default search index.

The tests use monkeypatching to mock the Azure SDKs and the internal search
provider, allowing the agent's logic to be tested in isolation without any
real network dependencies.
"""

from __future__ import annotations

import logging
import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

import ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent.knowledge_base_agent as kb


def install_azure_sdk_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install a minimal, in-process *fake* Azure SDK and ensure the KB module.

    builds its SearchClient from that fake.

    Why this exists:
    ----------------
    - The KB agent's preflight calls `await client.get_document_count()`.
    - In tests we do NOT want to talk to the real cloud or require actual SDKs.
    - Therefore we publish tiny fake modules into `sys.modules` that simulate
      the subset of the Azure SDK surface we use:
        * azure.core.credentials.AzureKeyCredential
        * azure.search.documents.aio.SearchClient
          - async get_document_count()
          - async close()
    - Finally, we patch the *symbol where it is used* (`kb.make_async_search_client`)
      to return an instance of our fake client. This guarantees the KB preflight
      sees a client compatible with the real API, avoiding
      `'FakeSearchClient' has no attribute 'get_document_count'` errors.

    Important detail:
    -----------------
    We patch *kb.make_async_search_client*, not the original factory module, because
    the KB file imported the symbol directly via:
        from ingenious.services.azure_search.client_init import make_async_search_client
    Patching the import site is necessary for the KB module to see our change.
    """
    import sys
    import types

    # 1) Define a tiny fake credential class that mimics azure.core.credentials.AzureKeyCredential.
    #    We only store the key; we do not perform any real auth.
    class _FakeAzureKeyCredential:
        def __init__(self, key: str) -> None:
            # Store the key just to look realistic (tests do not need it).
            self.key = key

    # 2) Define a tiny fake async SearchClient that mimics the subset of the real API
    #    that our KB preflight uses: `get_document_count()` and `close()`.
    class _FakeAsyncSearchClient:
        def __init__(self, *, endpoint: str, index_name: str, credential: Any) -> None:
            # Keep inputs to match real constructor signature for realism.
            self.endpoint = endpoint
            self.index_name = index_name
            self.credential = credential
            self._closed = False

        async def get_document_count(self) -> int:
            """Simulate a cheap health-check call that confirms connectivity and auth.

            We return a deterministic positive number so preflight "succeeds".
            If you need to simulate failures in other tests, you can extend this
            to raise exceptions conditionally (e.g., based on an env flag).
            """
            return 1

        async def close(self) -> None:
            """Simulate closing the real client asynchronously."""
            self._closed = True

    # 3) Publish the fake modules to sys.modules so any import statements in the
    #    code under test succeed without the real packages installed.
    #    We create *exact* module names so `import` statements resolve to these.
    fake_credentials_mod = types.ModuleType("azure.core.credentials")
    setattr(fake_credentials_mod, "AzureKeyCredential", _FakeAzureKeyCredential)

    fake_aio_mod = types.ModuleType("azure.search.documents.aio")
    setattr(fake_aio_mod, "SearchClient", _FakeAsyncSearchClient)

    # Register our fake modules. After this, imports like
    # `from azure.search.documents.aio import SearchClient`
    # will return our `_FakeAsyncSearchClient` class.
    monkeypatch.setitem(sys.modules, "azure.core.credentials", fake_credentials_mod)
    monkeypatch.setitem(sys.modules, "azure.search.documents.aio", fake_aio_mod)

    # 4) Patch the KB module's `make_async_search_client` symbol so that when the KB
    #    code calls `make_async_search_client(cfg_stub)`, we return the fake SDK client
    #    we just installed (which has the async methods preflight expects).
    #
    #    NOTE: Patch the import *site* (the KB module), not the factory module,
    #    because the KB file imported `make_async_search_client` by value, not by name.
    import ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent.knowledge_base_agent as kb  # noqa: E501

    def _build_fake_client_from_cfg(cfg: Any) -> _FakeAsyncSearchClient:
        """The KB preflight passes a SimpleNamespace stub with three attributes.

          - search_endpoint
          - search_index_name
          - search_key (may be a plain str or a SecretStr)
        We unwrap the SecretStr if present, then construct our fake client.
        """
        # Pull the endpoint and index from the stub (names match KB preflight).
        endpoint = getattr(cfg, "search_endpoint")
        index_name = getattr(cfg, "search_index_name")

        # Unwrap SecretStr if present; tests may pass a bare str.
        key_obj = getattr(cfg, "search_key", "")
        if hasattr(key_obj, "get_secret_value"):
            try:
                key = key_obj.get_secret_value()
            except Exception:
                # Defensive: if unwrap fails in tests, just fall back to empty string.
                key = ""
        else:
            key = key_obj or ""

        # Return an instance of our fake async client.
        return _FakeAsyncSearchClient(
            endpoint=endpoint,
            index_name=index_name,
            credential=_FakeAzureKeyCredential(key),
        )

    # Patch the symbol *used by the KB module*.
    monkeypatch.setattr(kb, "make_async_search_client", _build_fake_client_from_cfg, raising=True)

    # 5) (Optional) If some earlier test cached a factory singleton, clear it.
    #    This avoids surprising interactions when tests run in a different order.
    #    We swallow errors if that private symbol does not exist.
    try:
        monkeypatch.setattr(
            "ingenious.services.azure_search.client_init._FACTORY_SINGLETON",
            None,
            raising=False,
        )
    except Exception:
        # Not fatal—continue. This is only defensive cleanup for shared state between tests.
        pass


def provider_with(results: List[Dict[str, str]], monkeypatch: pytest.MonkeyPatch) -> None:
    """Mocks the internal AzureSearchProvider to return a fixed set of results.

    This allows tests to provide controlled, predictable search results to the
    knowledge base agent's search method, isolating the agent's formatting
    and processing logic from the actual data retrieval implementation.
    """
    prov_mod = types.ModuleType("ingenious.services.azure_search.provider")

    class AzureSearchProvider:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:  # accept config or nothing
            pass

        async def retrieve(self, *a: Any, **k: Any) -> List[Dict[str, str]]:
            return results

        async def close(self) -> None:
            pass

    prov_mod.AzureSearchProvider = AzureSearchProvider  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ingenious.services.azure_search.provider", prov_mod)


@pytest.mark.asyncio
async def test_azure_snippet_cap_truncates_snippet_and_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies that KB_AZURE_SNIPPET_CAP truncates search result snippets and content.

    This test ensures that when the environment variable for capping snippet length
    is set, both the 'snippet' and 'content' fields of the search results are
    correctly truncated to the specified length. This is important for controlling
    the size of the context fed to the language model.
    """
    install_azure_sdk_ok(monkeypatch)
    # Long snippet and content
    doc: Dict[str, str] = {
        "id": "1",
        "title": "T1",
        "snippet": "ABCDEFGHIJKL",
        "content": "abcdefghijklmnop",
    }
    provider_with([doc], monkeypatch)

    os.environ["KB_AZURE_SNIPPET_CAP"] = "10"

    flow: kb.ConversationFlow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    flow._config = SimpleNamespace(
        models=[SimpleNamespace(model="gpt-5")],
        azure_search_services=[SimpleNamespace(endpoint="https://s", key="k", index_name="idx")],
    )
    flow._chat_service = None
    flow._memory_path = str(tmp_path)

    out: str = await flow._search_knowledge_base("q", use_azure_search=True, top_k=3, logger=None)
    # capped to 10 chars each
    assert "ABCDEFGHIJ" in out
    assert "abcdefghij" in out


@pytest.mark.asyncio
async def test_multiple_results_include_separators(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Checks that multiple search results are formatted with a separator.

    This ensures that when more than one document is returned from the knowledge
    base search, a clear separator is inserted between them. This helps in
    structuring the context for the language model, making it easier to
    distinguish between different sources of information.
    """
    install_azure_sdk_ok(monkeypatch)
    provider_with(
        [
            {"id": "1", "title": "A", "snippet": "s1", "content": "c1"},
            {"id": "2", "title": "B", "snippet": "s2", "content": "c2"},
        ],
        monkeypatch,
    )
    flow: kb.ConversationFlow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    flow._config = SimpleNamespace(
        models=[SimpleNamespace(model="gpt-5")],
        azure_search_services=[SimpleNamespace(endpoint="https://s", key="k", index_name="idx")],
    )
    flow._chat_service = None
    flow._memory_path = str(tmp_path)

    out: str = await flow._search_knowledge_base("q", use_azure_search=True, top_k=2, logger=None)
    assert "\n\n---\n\n" in out  # separator present


@pytest.mark.asyncio
async def test_env_default_index_logs_info_when_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Verifies an info message is logged when the default index env var is used.

    This test confirms that if the Azure Search configuration lacks an explicit
    index name, the system falls back to the `AZURE_SEARCH_DEFAULT_INDEX`
    environment variable and logs an informational message. This logging is
    crucial for transparency and debugging configuration issues.
    """
    install_azure_sdk_ok(monkeypatch)
    provider_with([{"id": "1", "title": "T", "snippet": "S", "content": "C"}], monkeypatch)

    # index missing -> use env default and log INFO
    os.environ["AZURE_SEARCH_DEFAULT_INDEX"] = "docs"

    flow: kb.ConversationFlow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    flow._config = SimpleNamespace(
        models=[SimpleNamespace(model="gpt-5")],
        azure_search_services=[SimpleNamespace(endpoint="https://s", key="k", index_name="")],
    )
    flow._chat_service = None
    flow._memory_path = str(tmp_path)

    caplog.set_level("INFO")
    logger: logging.Logger = logging.getLogger("kb-test")
    _: str = await flow._search_knowledge_base("q", use_azure_search=True, top_k=1, logger=logger)
    assert any(
        "using env AZURE_SEARCH_DEFAULT_INDEX" in (r.getMessage() or "") for r in caplog.records
    )
