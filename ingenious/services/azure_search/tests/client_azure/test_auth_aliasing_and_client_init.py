"""Test Azure config aliasing and client factory wiring.

This module contains small, focused tests that validate (1) alias handling in
Azure authentication configuration, and (2) that Azure search/OpenAI client
creation delegates to the factory layer. Tests intentionally reload target
modules to avoid state leakage across runs. The key entry points here are
`test_auth_aliasing_maps_keys_and_endpoint` and
`test_client_init_delegates_to_factory`, with `_reload` as a helper.
Dependencies: `pydantic.SecretStr`, pytest's `MonkeyPatch` fixture, and the
runtime `ingenious.*` packages. Run with `pytest -q`.
"""

from __future__ import annotations

import importlib
import sys
import types
from typing import TYPE_CHECKING, Any, cast

from pydantic import SecretStr

if TYPE_CHECKING:
    # pytest may not ship type stubs in all environments; used for annotations only.
    from _pytest.monkeypatch import MonkeyPatch


def _reload(module_name: str) -> types.ModuleType:
    """Reload a module by name, importing it if not already loaded.

    This keeps tests isolated from each other's import-time side effects by
    ensuring a fresh module state when needed.

    Args:
        module_name: Fully qualified module path to (re)load.

    Returns:
        The loaded module object.
    """
    if module_name in sys.modules:
        importlib.reload(sys.modules[module_name])
    else:
        __import__(module_name)
    return sys.modules[module_name]


def test_auth_aliasing_maps_keys_and_endpoint() -> None:
    """Verify config aliasing maps keys and endpoint correctly.

    The test asserts that `AzureAuthConfig.from_config` accepts alternate key
    names (e.g., `search_key`, `openai_key`, `openai_endpoint`) and maps them
    to the canonical fields (`api_key`, `endpoint`).
    """
    # Cast to Any so we can access dynamic attributes exported by the module.
    auth_mod: Any = cast(Any, _reload("ingenious.config.auth_config"))
    AzureAuthConfig = auth_mod.AzureAuthConfig

    cfg1: dict[str, str] = {"search_key": "S"}
    a1 = AzureAuthConfig.from_config(cfg1)
    assert a1.api_key == "S"

    cfg2: dict[str, str] = {"openai_key": "O", "openai_endpoint": "https://aoai"}
    a2 = AzureAuthConfig.from_config(cfg2)
    assert a2.api_key == "O"
    assert a2.endpoint == "https://aoai"


def test_client_init_delegates_to_factory(monkeypatch: "MonkeyPatch") -> None:
    """Ensure client init delegates to the Azure client factory methods.

    This test patches the factory's creation methods to record calls and return
    sentinels. It then verifies that `make_async_search_client` and
    `make_async_openai_client` invoke those factory methods.

    Args:
        monkeypatch: Pytest fixture used to patch attributes during the test.
    """
    fac_mod: Any = cast(
        Any, _reload("ingenious.client.azure.azure_client_builder_factory")
    )
    called: dict[str, bool] = {"search": False, "openai": False}

    def fake_search(
        index_name: str, config: dict[str, Any] | None = None, **opts: Any
    ) -> object:
        """Return a sentinel for search client creation and mark invocation.

        Args:
            index_name: Name of the search index.
            config: Optional config mapping passed through by the caller.
            **opts: Additional factory options.

        Returns:
            A generic sentinel object.
        """
        called["search"] = True
        return object()

    def fake_openai(
        config: dict[str, Any] | None = None,
        api_version: str | None = None,
        **opts: Any,
    ) -> object:
        """Return a sentinel for OpenAI client creation and mark invocation.

        Args:
            config: Optional config mapping passed through by the caller.
            api_version: Optional OpenAI API version string.
            **opts: Additional factory options.

        Returns:
            A generic sentinel object.
        """
        called["openai"] = True
        return object()

    monkeypatch.setattr(
        fac_mod.AzureClientFactory,
        "create_async_search_client",
        staticmethod(fake_search),
    )
    monkeypatch.setattr(
        fac_mod.AzureClientFactory,
        "create_async_openai_client",
        staticmethod(fake_openai),
    )

    client_init: Any = cast(Any, _reload("ingenious.services.azure_search.client_init"))
    cfg_mod: Any = cast(Any, _reload("ingenious.services.azure_search.config"))
    SearchConfig = cfg_mod.SearchConfig

    cfg = SearchConfig(
        search_endpoint="https://s",
        search_key=SecretStr("sk"),
        search_index_name="idx",
        openai_endpoint="https://o",
        openai_key=SecretStr("ok"),
        openai_version="2024-02-01",
        embedding_deployment_name="emb",
        generation_deployment_name="gen",
        use_semantic_ranking=False,
        top_k_retrieval=5,
        top_n_final=3,
    )

    sc = client_init.make_async_search_client(cfg)
    oc = client_init.make_async_openai_client(cfg)
    assert called["search"] is True
    assert called["openai"] is True
    assert sc is not None and oc is not None
