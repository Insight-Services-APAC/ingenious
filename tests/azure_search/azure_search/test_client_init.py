# -*- coding: utf-8 -*-
"""Unit tests for the async Azure client initialization helpers in.

`ingenious.services.azure_search.client_init`.

This module validates the following contract:

1) The thin wrapper functions in `client_init`:
   - `make_async_search_client(cfg, **client_options)`
   - `make_async_openai_client(cfg, **client_options)`
   forward configuration and client options to the central `AzureClientFactory`.
   They unwrap secrets (e.g., `SecretStr`) but otherwise remain pass-through.

2) The builders used by the factory perform the actual, production logic:
   - For **OpenAI (async)**:
       * Map config fields to SDK kwargs (`azure_endpoint`, `api_key`, `api_version`).
       * Normalize the `retries` alias to `max_retries`.
       * Apply a sensible default `max_retries=3` when not provided by caller/config.
       * Filter unknown kwargs so strict test doubles (without `**kwargs`) do not error.

   - For **Azure Search (async)**:
       * Map config to `endpoint`, `index_name`, and credential (via `AzureKeyCredential`
         when a key is provided).
       * Pass through any optional `client_options` to the SDK constructor without
         attempting alias normalization (these are azure-core/azure-search kwargs).
         (Optionally, the builder may filter unknown kwargs defensively.)

To avoid real SDK dependencies or network calls, the tests install **dummy modules**
into `sys.modules` which implement the minimal constructor shape needed for assertions.
We then **evict** the factory/builder modules from the import cache and reload the
`client_init` module so that all imports bind to the fresh dummies.

Why the eviction step matters:
- If a previous test already imported `ingenious.client.azure.builder.search_client_async`,
  it captured a reference to a *prior* `DummySearchClient` class. Creating a new dummy
  class with the same name in this test would not be `isinstance`-compatible due to
  different class identity. Evicting and re-importing ensures everyone uses the same
  class objects created in this test run.
"""

from __future__ import annotations

import importlib
import sys
import types
from typing import Any

import pytest
from pydantic import SecretStr

from ingenious.services.azure_search.config import SearchConfig


def _install_dummy_sdk_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, type[Any]]:
    """Install minimal dummy SDK modules into sys.modules for testing.

    We emulate only the small subset of SDK surface needed by the code under test:
      - azure.core.credentials.AzureKeyCredential
      - azure.search.documents.aio.SearchClient (async)
      - openai.AsyncAzureOpenAI

    The `SearchClient` dummy accepts **kwargs and captures them in `extra_kwargs`.
    The `AsyncAzureOpenAI` dummy is intentionally STRICT: it *only* accepts
    keyword-only args (no **kwargs) to verify the builder filters unknown kwargs.

    Returns:
        dict[str, type[Any]]: A mapping of class names to dummy class types for isinstance checks.
    """

    # --- azure.core.credentials.AzureKeyCredential ---------------------------
    class DummyAzureKeyCredential:
        """A dummy replacement for AzureKeyCredential that captures the key string."""

        def __init__(self, key: str) -> None:
            self.key = key

    # --- azure.search.documents.aio.SearchClient -----------------------------
    class DummySearchClient:
        """A dummy async SearchClient that captures constructor arguments and any extra kwargs.

        It accepts **kwargs to mirror the real SDK's permissive constructor surface,
        allowing tests to verify pass-through of client_options.
        """

        def __init__(
            self,
            *,
            endpoint: str,
            index_name: str,
            credential: DummyAzureKeyCredential,
            **kwargs: Any,
        ) -> None:
            self.endpoint = endpoint
            self.index_name = index_name
            self.credential = credential
            self.extra_kwargs = kwargs  # capture passthrough options

    # --- openai.AsyncAzureOpenAI --------------------------------------------
    class DummyAsyncAzureOpenAI:
        """A strict dummy of AsyncAzureOpenAI that matches the expected constructor.

        NOTE: No **kwargs on purpose, so passing unknown options would raise TypeError
        unless the builder filters them out.
        """

        def __init__(
            self,
            *,
            azure_endpoint: str,
            api_key: str,
            api_version: str,
            max_retries: int,
        ) -> None:
            self.azure_endpoint = azure_endpoint
            self.api_key = api_key
            self.api_version = api_version
            self.max_retries = max_retries

    # Build module objects and register them in sys.modules so imports resolve to dummies.
    azure = types.ModuleType("azure")
    core = types.ModuleType("azure.core")
    credentials = types.ModuleType("azure.core.credentials")
    credentials.AzureKeyCredential = DummyAzureKeyCredential  # type: ignore[attr-defined]

    search = types.ModuleType("azure.search")
    documents = types.ModuleType("azure.search.documents")
    aio = types.ModuleType("azure.search.documents.aio")
    aio.SearchClient = DummySearchClient  # type: ignore[attr-defined]

    openai_mod = types.ModuleType("openai")
    openai_mod.AsyncAzureOpenAI = DummyAsyncAzureOpenAI  # type: ignore[attr-defined]

    # Install in sys.modules via monkeypatch (auto-restore per test).
    monkeypatch.setitem(sys.modules, "azure", azure)
    monkeypatch.setitem(sys.modules, "azure.core", core)
    monkeypatch.setitem(sys.modules, "azure.core.credentials", credentials)
    monkeypatch.setitem(sys.modules, "azure.search", search)
    monkeypatch.setitem(sys.modules, "azure.search.documents", documents)
    monkeypatch.setitem(sys.modules, "azure.search.documents.aio", aio)
    monkeypatch.setitem(sys.modules, "openai", openai_mod)

    return {
        "AzureKeyCredential": DummyAzureKeyCredential,
        "SearchClient": DummySearchClient,
        "AsyncAzureOpenAI": DummyAsyncAzureOpenAI,
    }


def _reload_client_init_with_dummies(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[types.ModuleType, dict[str, type[Any]]]:
    """Install dummy SDKs and then ensure that the factory/builders and client_init.

    bind to those dummy modules, even if they were imported earlier.

    Implementation detail:
      1) Install dummy azure/openai modules.
      2) Evict the relevant `ingenious.client.azure` modules from sys.modules
         (factory + builders + client_init), so new imports bind to the new dummies.
      3) Import and return the freshly loaded client_init.

    Returns:
        tuple[module, dict[str, type]]: (reloaded client_init module, dummy type map)
    """
    dummies = _install_dummy_sdk_modules(monkeypatch)

    # Evict factory/builders so new import uses the dummies we just installed.
    for modname in [
        # Builders that bind to azure/openai at import time
        "ingenious.client.azure.builder.search_client_async",
        "ingenious.client.azure.builder.openai_client_async",
        # Central factory that imports builders lazily
        "ingenious.client.azure.azure_client_builder_factory",
        # The package that exposes AzureClientFactory
        "ingenious.client.azure",
        # The module under test (thin wrapper)
        "ingenious.services.azure_search.client_init",
    ]:
        sys.modules.pop(modname, None)

    # Now import the module under test so it binds to the fresh modules above.
    import ingenious.services.azure_search.client_init as client_init  # noqa: E402

    # One more reload for good measure; not strictly necessary after pop, but harmless.
    client_init = importlib.reload(client_init)
    return client_init, dummies


def _make_cfg(**overrides: Any) -> SearchConfig:
    """Create a valid SearchConfig with reasonable defaults for tests.

    The defaults include both Search and OpenAI endpoints/keys so we can exercise
    both `make_async_search_client` and `make_async_openai_client` in one place.
    Any field can be overridden by passing keyword arguments.
    """
    data: dict[str, Any] = dict(
        search_endpoint="https://s.example.net",
        search_key=SecretStr("search-secret"),
        search_index_name="my-index",
        openai_endpoint="https://oai.example.com",
        openai_key=SecretStr("openai-secret"),
        embedding_deployment_name="emb-deploy",
        generation_deployment_name="gen-deploy",
        # openai_version may be provided via overrides (explicit mapping test)
    )
    data.update(overrides)
    return SearchConfig(**data)


# --------------------------------------------------------------------------------------
#                                      TESTS
# --------------------------------------------------------------------------------------


def test_make_async_search_client_uses_secretstr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure `make_async_search_client` unwraps SecretStr for the AzureKeyCredential and maps fields.

    Assertions:
      - The returned object is the dummy SearchClient.
      - endpoint and index_name map correctly from config.
      - The credential is AzureKeyCredential with the raw key string (not SecretStr).
    """
    client_init, d = _reload_client_init_with_dummies(monkeypatch)

    cfg = _make_cfg()
    sc: Any = client_init.make_async_search_client(cfg)

    assert isinstance(sc, d["SearchClient"])
    assert sc.endpoint == cfg.search_endpoint
    assert sc.index_name == cfg.search_index_name

    # SecretStr was unwrapped (the dummy captures the raw key).
    assert isinstance(sc.credential, d["AzureKeyCredential"])
    assert sc.credential.key == "search-secret"


def test_make_async_openai_client_maps_version_and_max_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify `make_async_openai_client` + builder map values and ensure default max_retries.

    This test validates:
      - Mapping: `openai_endpoint` -> azure_endpoint, `openai_key` -> api_key,
                 cfg.openai_version -> api_version (explicitly provided in test).
      - Secret unwrapping for api_key.
      - Builder injects a default `max_retries=3` when caller provides none.
    """
    client_init, d = _reload_client_init_with_dummies(monkeypatch)

    cfg = _make_cfg(openai_version="2025-01-01")
    oc: Any = client_init.make_async_openai_client(cfg)

    assert isinstance(oc, d["AsyncAzureOpenAI"])
    assert oc.azure_endpoint == cfg.openai_endpoint
    assert oc.api_key == "openai-secret"  # SecretStr unwrapped
    assert oc.api_version == "2025-01-01"  # explicit version mapped
    assert oc.max_retries == 3  # default applied by builder


def test_make_async_openai_client_respects_explicit_max_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the caller passes `max_retries`, the builder should honor that value verbatim."""
    client_init, d = _reload_client_init_with_dummies(monkeypatch)
    cfg = _make_cfg(openai_version="2025-01-01")

    oc: Any = client_init.make_async_openai_client(cfg, max_retries=7)

    assert isinstance(oc, d["AsyncAzureOpenAI"])
    assert oc.max_retries == 7


def test_make_async_openai_client_normalizes_retries_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the caller passes the alias `retries`, normalize it to `max_retries`.

    The builder is responsible for translating aliases; the wrapper simply forwards.
    """
    client_init, d = _reload_client_init_with_dummies(monkeypatch)
    cfg = _make_cfg(openai_version="2025-01-01")

    oc: Any = client_init.make_async_openai_client(cfg, retries=5)

    assert isinstance(oc, d["AsyncAzureOpenAI"])
    assert oc.max_retries == 5


def test_make_async_openai_client_drops_unknown_kwargs_without_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown kwargs must not reach the SDK constructor.

    Our strict dummy for AsyncAzureOpenAI does not accept **kwargs; the builder must
    filter out unrecognized options to avoid TypeError and still create the client.
    """
    client_init, d = _reload_client_init_with_dummies(monkeypatch)
    cfg = _make_cfg(openai_version="2025-01-01")

    # 'foo' is not a valid constructor kwarg for the dummy; it should be dropped.
    oc: Any = client_init.make_async_openai_client(cfg, foo="bar")

    assert isinstance(oc, d["AsyncAzureOpenAI"])
    # The dummy exposes only known attributes; presence of 'foo' would imply a leak.
    assert not hasattr(oc, "foo")


def test_make_async_search_client_forwards_client_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Search builder/wrapper should forward client_options to the SDK constructor.

    The dummy SearchClient stores unrecognized kwargs in `extra_kwargs`; verifying
    those values confirms pass-through behavior on the Search path.

    NOTE: This test previously failed with a false-negative isinstance because the
    builder module had already been imported in another test, holding onto a prior
    DummySearchClient class. We now evict and reload modules in the helper to avoid
    class-identity mismatches.
    """
    client_init, d = _reload_client_init_with_dummies(monkeypatch)
    cfg = _make_cfg()

    sc: Any = client_init.make_async_search_client(cfg, http_logging_policy=True, my_opt=123)

    assert isinstance(sc, d["SearchClient"])
    assert sc.extra_kwargs.get("http_logging_policy") is True
    assert sc.extra_kwargs.get("my_opt") == 123


def test_make_async_openai_client_rejects_negative_max_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation guard: negative values for `max_retries` must raise ValueError.

    This ensures the builder enforces sane bounds on retry settings.
    """
    client_init, _ = _reload_client_init_with_dummies(monkeypatch)
    cfg = _make_cfg(openai_version="2025-01-01")

    with pytest.raises(ValueError, match="max_retries must be >= 0"):
        client_init.make_async_openai_client(cfg, max_retries=-1)
