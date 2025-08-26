"""Test async Azure client builders and factory.

These tests validate the behavior of the asynchronous Azure client builders and
their factory wrappers in the `ingenious.client.azure` package. They exercise
both API key and AAD token credential paths, ensure endpoint construction from
a short "service" name, and verify option forwarding. A lightweight module
reloader is used so each test sees the latest module state. Tests rely on local
"stub" azure packages—no real network calls are made.

Entry points under test:
- ingenious.client.azure.builder.search_client_async.AzureSearchAsyncClientBuilder
- ingenious.client.azure.builder.openai_client_async.AsyncAzureOpenAIClientBuilder
- ingenious.client.azure.azure_client_builder_factory.AzureClientFactory
"""

from __future__ import annotations

import importlib
import sys
from types import ModuleType

import pytest


def _reload(module_name: str) -> ModuleType:
    """Reload a module by name and return the live module object.

    This helper ensures tests observe fresh module state on each call
    without requiring a full interpreter restart.

    Args:
        module_name: Dotted module path to reload or import.

    Returns:
        ModuleType: The (re)loaded module object.
    """
    if module_name in sys.modules:
        importlib.reload(sys.modules[module_name])
    else:
        __import__(module_name)
    return sys.modules[module_name]


def test_async_search_builder_api_key_path() -> None:
    """Build async Search client via API key and assert core properties."""
    builder_mod: ModuleType = _reload(
        "ingenious.client.azure.builder.search_client_async"
    )
    AzureSearchAsyncClientBuilder = builder_mod.AzureSearchAsyncClientBuilder

    cfg: dict[str, str] = {
        "search_endpoint": "https://example.search.windows.net",
        "search_key": "S_KEY",
    }
    b = AzureSearchAsyncClientBuilder.from_config(cfg, index_name="idx")
    client = b.build()

    from azure.core.credentials import (
        AzureKeyCredential,  # stubbed
    )

    assert client.endpoint == "https://example.search.windows.net"
    assert client.index_name == "idx"
    assert isinstance(client.credential, AzureKeyCredential)


def test_async_search_builder_prefers_token_over_key() -> None:
    """Prefer TokenCredential over API key when both are supplied."""
    builder_mod: ModuleType = _reload(
        "ingenious.client.azure.builder.search_client_async"
    )
    AzureSearchAsyncClientBuilder = builder_mod.AzureSearchAsyncClientBuilder

    # Provide BOTH SP credentials and a key; must prefer TokenCredential (AAD)
    cfg: dict[str, str] = {
        "search_endpoint": "https://example.search.windows.net",
        "search_key": "S_KEY",
        "client_id": "cid",
        "client_secret": "csec",
        "tenant_id": "tid",
    }
    b = AzureSearchAsyncClientBuilder.from_config(
        cfg, index_name="idx", client_options={"user_agent": "ua"}
    )
    client = b.build()

    from azure.identity.aio import (
        ClientSecretCredential,  # stubbed
    )

    assert isinstance(client.credential, ClientSecretCredential)
    assert client.kwargs.get("user_agent") == "ua"


def test_async_search_builder_service_fallback_builds_endpoint() -> None:
    """Construct endpoint from `service` when full endpoint not provided."""
    builder_mod: ModuleType = _reload(
        "ingenious.client.azure.builder.search_client_async"
    )
    AzureSearchAsyncClientBuilder = builder_mod.AzureSearchAsyncClientBuilder

    cfg: dict[str, str] = {"service": "mysearchacct", "search_key": "S_KEY"}
    b = AzureSearchAsyncClientBuilder.from_config(cfg, index_name="idx")
    client = b.build()

    assert client.endpoint == "https://mysearchacct.search.windows.net"
    assert client.index_name == "idx"


def test_async_openai_builder_api_key_path() -> None:
    """Build Async Azure OpenAI client via API key and assert properties."""
    builder_mod: ModuleType = _reload(
        "ingenious.client.azure.builder.openai_client_async"
    )
    AsyncAzureOpenAIClientBuilder = builder_mod.AsyncAzureOpenAIClientBuilder

    cfg: dict[str, str] = {
        "openai_endpoint": "https://example.openai.azure.com",
        "openai_key": "O_KEY",
        "api_version": "2024-02-01",
    }
    b = AsyncAzureOpenAIClientBuilder.from_config(cfg)
    client = b.build()

    assert client.azure_endpoint == "https://example.openai.azure.com"
    assert client.api_version == "2024-02-01"
    assert client.api_key == "O_KEY"
    assert client.azure_ad_token_provider is None


def test_async_openai_builder_aad_path() -> None:
    """Build Async Azure OpenAI client via AAD when no key is provided."""
    builder_mod: ModuleType = _reload(
        "ingenious.client.azure.builder.openai_client_async"
    )
    AsyncAzureOpenAIClientBuilder = builder_mod.AsyncAzureOpenAIClientBuilder

    cfg: dict[str, str] = {
        "openai_endpoint": "https://example.openai.azure.com"
    }  # no key => use AAD default
    b = AsyncAzureOpenAIClientBuilder.from_config(cfg, api_version="2024-02-01")
    client = b.build()

    assert client.azure_endpoint == "https://example.openai.azure.com"
    assert client.api_version == "2024-02-01"
    assert client.azure_ad_token_provider is not None
    assert callable(client.azure_ad_token_provider)
    assert client.azure_ad_token_provider() == "aad-bearer-token"


def test_factory_async_methods_select_and_forward() -> None:
    """Verify factory creates clients and forwards options correctly."""
    fac_mod: ModuleType = _reload("ingenious.client.azure.azure_client_builder_factory")
    AzureClientFactory = fac_mod.AzureClientFactory

    # Search client (key path)
    cfg_search: dict[str, str] = {
        "search_endpoint": "https://ex.search.windows.net",
        "search_key": "K",
    }
    s_client = AzureClientFactory.create_async_search_client(
        index_name="myindex", config=cfg_search
    )
    assert s_client.index_name == "myindex"

    # OpenAI client (key path)
    cfg_aoai: dict[str, str] = {
        "openai_endpoint": "https://ex.openai.azure.com",
        "openai_key": "K",
        "api_version": "2024-02-01",
    }
    o_client = AzureClientFactory.create_async_openai_client(config=cfg_aoai)
    assert o_client.api_key == "K"


@pytest.mark.asyncio
async def test_create_async_search_client_prefers_token() -> None:
    """Ensure factory prefers AAD token when both token and key are present."""
    fac_mod: ModuleType = _reload("ingenious.client.azure.azure_client_builder_factory")
    AzureClientFactory = fac_mod.AzureClientFactory

    cfg: dict[str, str] = {
        "search_endpoint": "https://example.search.windows.net",
        "search_key": "KEY",
        "client_id": "cid",
        "client_secret": "csec",
        "tenant_id": "tid",
    }
    client = AzureClientFactory.create_async_search_client(index_name="idx", config=cfg)

    from azure.identity.aio import (
        ClientSecretCredential,
    )

    assert isinstance(client.credential, ClientSecretCredential)
    # Exercise async method to satisfy pytest-asyncio path
    await client.close()
