"""Extra coverage for Azure auth & sync search builder edges.

Covers:
- MSI (with/without client_id) in async builder
- DEFAULT_CREDENTIAL path when no key present
- Sync SearchClientBuilder: service→endpoint fallback, required fields
- Factory guard: HAS_SEARCH=False ImportError text
- Deterministic ImportError when azure-identity missing (builder base)
"""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from typing import Any

import pytest

# --------------------------- helpers: stub modules ---------------------------


def _install_async_search_stubs(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Install minimal azure async SDK stubs so builders can import."""
    created: dict[str, Any] = {}

    # azure.core.credentials.AzureKeyCredential
    core_creds = types.ModuleType("azure.core.credentials")

    class AzureKeyCredential:  # noqa: N801
        def __init__(self, key: str) -> None:
            self.key = key

    core_creds.AzureKeyCredential = AzureKeyCredential
    monkeypatch.setitem(sys.modules, "azure.core.credentials", core_creds)
    created["AzureKeyCredential"] = AzureKeyCredential

    # azure.core.credentials_async.AsyncTokenCredential (typing only)
    core_async = types.ModuleType("azure.core.credentials_async")

    class AsyncTokenCredential:  # noqa: N801
        async def get_token(self, *scopes: str) -> Any:  # pragma: no cover
            return None

    core_async.AsyncTokenCredential = AsyncTokenCredential
    monkeypatch.setitem(sys.modules, "azure.core.credentials_async", core_async)

    # azure.identity.aio credentials
    id_aio = types.ModuleType("azure.identity.aio")

    class DefaultAzureCredential:  # noqa: N801
        def __init__(self, *_, **__) -> None: ...

    class ManagedIdentityCredential:  # noqa: N801
        def __init__(self, *_, **__) -> None: ...

    class ClientSecretCredential:  # noqa: N801
        def __init__(self, *_, **__) -> None: ...

    id_aio.DefaultAzureCredential = DefaultAzureCredential
    id_aio.ManagedIdentityCredential = ManagedIdentityCredential
    id_aio.ClientSecretCredential = ClientSecretCredential
    monkeypatch.setitem(sys.modules, "azure.identity.aio", id_aio)
    created.update(
        {
            "DefaultAzureCredential": DefaultAzureCredential,
            "ManagedIdentityCredential": ManagedIdentityCredential,
            "ClientSecretCredential": ClientSecretCredential,
        }
    )

    # azure.search.documents.aio.SearchClient that records the credential
    az_aio = types.ModuleType("azure.search.documents.aio")

    class SearchClient:  # noqa: N801
        def __init__(self, *, endpoint: str, index_name: str, credential: Any, **_: Any) -> None:
            self.endpoint = endpoint
            self.index_name = index_name
            self.credential = credential

    az_aio.SearchClient = SearchClient
    monkeypatch.setitem(sys.modules, "azure.search.documents.aio", az_aio)
    created["AsyncSearchClient"] = SearchClient

    # Sync search client for sync builder
    az_sync = types.ModuleType("azure.search.documents")

    class SyncSearchClient:  # noqa: N801
        def __init__(self, *, endpoint: str, index_name: str, credential: Any, **_: Any) -> None:
            self.endpoint = endpoint
            self.index_name = index_name
            self.credential = credential

    az_sync.SearchClient = SyncSearchClient
    monkeypatch.setitem(sys.modules, "azure.search.documents", az_sync)
    created["SyncSearchClient"] = SyncSearchClient

    return created


# ------------------------------- MSI variants --------------------------------


def test_async_search_builder_msi_with_and_without_client_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Async builder should use ManagedIdentityCredential both with and without client_id."""
    stubs = _install_async_search_stubs(monkeypatch)

    # Import after stubs
    from ingenious.client.azure.builder.search_client_async import (
        AzureSearchAsyncClientBuilder,
    )

    endpoint = "https://x.search.windows.net"
    cfg_without: dict[str, Any] = {"endpoint": endpoint, "search_key": None}
    cfg_with: dict[str, Any] = {
        "endpoint": endpoint,
        "managed_identity_client_id": "abc-123",
    }

    # Without explicit client_id (SAMI)
    b1 = AzureSearchAsyncClientBuilder.from_config(cfg_without, index_name="idx")
    c1 = b1.build()
    assert isinstance(c1.credential, stubs["DefaultAzureCredential"])

    # With client_id (UAMI)
    b2 = AzureSearchAsyncClientBuilder.from_config(cfg_with, index_name="idx")
    c2 = b2.build()
    assert isinstance(c2.credential, stubs["ManagedIdentityCredential"])


def test_async_search_builder_default_credential_when_prefer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no key and prefer_token is truthy, DefaultAzureCredential should be used."""
    stubs = _install_async_search_stubs(monkeypatch)
    from ingenious.client.azure.builder.search_client_async import (
        AzureSearchAsyncClientBuilder,
    )

    cfg = {"endpoint": "https://x.search.windows.net", "prefer_token": True}
    b = AzureSearchAsyncClientBuilder.from_config(cfg, index_name="idx")
    client = b.build()
    assert isinstance(client.credential, stubs["DefaultAzureCredential"])


# ------------------------------ sync builder ---------------------------------


def test_sync_search_builder_service_fallback_and_required_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sync AzureSearchClientBuilder: service→endpoint fallback and validation errors."""
    _install_async_search_stubs(monkeypatch)  # installs sync SearchClient too
    from ingenious.client.azure.builder.search_client import AzureSearchClientBuilder

    # Service fallback builds endpoint
    cfg = SimpleNamespace(service="svc", key="K")
    b = AzureSearchClientBuilder(cfg, index_name="idx")
    c = b.build()
    assert c.endpoint == "https://svc.search.windows.net"
    assert c.index_name == "idx"

    # Missing index_name → ValueError
    with pytest.raises(ValueError, match="Index name is required"):
        AzureSearchClientBuilder(cfg, index_name=None).build()  # type: ignore[arg-type]

    # Missing endpoint and service → ValueError
    cfg_bad = SimpleNamespace(endpoint=None, service=None, key="K")
    with pytest.raises(ValueError, match="Endpoint is required"):
        AzureSearchClientBuilder(cfg_bad, index_name="idx").build()


def test_factory_create_search_client_requires_sdk_when_has_search_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Factory should raise a deterministic message when HAS_SEARCH=False."""
    from ingenious.client.azure import azure_client_builder_factory as f

    monkeypatch.setattr(f, "HAS_SEARCH", False, raising=True)
    with pytest.raises(ImportError, match="azure-search-documents is required"):
        f.AzureClientFactory.create_search_client_from_params(
            endpoint="https://x", index_name="idx", api_key="k"
        )


def test_builder_base_identity_missing_error_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Base builder should raise a clear ImportError when azure-identity is missing."""
    # Ensure any prior injected identity modules are gone
    for name in list(sys.modules):
        if name.startswith("azure.identity"):
            sys.modules.pop(name, None)

    # Import after purging identity so the base will try runtime import and fail
    from ingenious.client.azure.builder.base import AzureClientBuilder
    from ingenious.common.enums import AuthenticationMethod
    from ingenious.config.auth_config import AzureAuthConfig

    class _Dummy(AzureClientBuilder):
        def build(self) -> None:  # pragma: no cover - not used
            return None

    builder = _Dummy(
        auth_config=AzureAuthConfig(authentication_method=AuthenticationMethod.DEFAULT_CREDENTIAL)
    )
    with pytest.raises(ImportError, match="azure-identity is required for AAD authentication"):
        _ = builder.credential
