"""Tests for the async Azure Search client builder.

Ensures that the credential resolution logic correctly prioritizes different
authentication methods. Specifically, this module verifies that when both an API key
and client-secret credentials are provided, the builder correctly selects the
client-secret method.

This test file uses monkeypatching to install fake (stubbed) versions of the Azure
SDK modules, preventing any real network calls and isolating the builder's logic.

Key entry points:
- `test_async_builder_client_secret_over_key`: The main test case.
"""

from __future__ import annotations

import sys
import types
from typing import Any, AsyncIterator, NoReturn, Self

from pytest import MonkeyPatch

# Test constants for configuration
TEST_ENDPOINT = "https://x.search.windows.net"
TEST_SEARCH_KEY = "should_not_be_used"
TEST_TENANT_ID = "t"
TEST_CLIENT_ID = "c"
TEST_CLIENT_SECRET = "s"
TEST_INDEX_NAME = "idx"


def _install_async_stubs(monkeypatch: MonkeyPatch) -> dict[str, type]:
    """Install fake Azure SDK modules to isolate the builder from network calls.

    This function creates and injects stubbed versions of necessary Azure SDK
    classes (`SearchClient`, credentials, etc.) into `sys.modules`. This allows
    testing the client builder's logic without requiring actual Azure credentials
    or making network requests.

    Args:
        monkeypatch: The pytest fixture for modifying modules, classes, or functions.

    Returns:
        A dictionary mapping the names of the stubbed classes to the classes
        themselves, for use in assertions.
    """
    created: dict[str, type] = {}

    core = types.ModuleType("azure.core.credentials")

    class AzureKeyCredential:  # noqa: N801
        """A stub for azure.core.credentials.AzureKeyCredential."""

        def __init__(self, key: str) -> None:
            self.key = key

    core.AzureKeyCredential = AzureKeyCredential
    monkeypatch.setitem(sys.modules, "azure.core.credentials", core)
    created["AzureKeyCredential"] = AzureKeyCredential

    aio = types.ModuleType("azure.identity.aio")

    class ClientSecretCredential:  # noqa: N801
        """A stub for azure.identity.aio.ClientSecretCredential."""

        def __init__(self, *_: Any, **__: Any) -> None: ...

    class DefaultAzureCredential:  # noqa: N801
        """A stub for azure.identity.aio.DefaultAzureCredential."""

        def __init__(self, *_: Any, **__: Any) -> None: ...

    class ManagedIdentityCredential:  # noqa: N801
        """A stub for azure.identity.aio.ManagedIdentityCredential."""

        def __init__(self, *_: Any, **__: Any) -> None: ...

    aio.ClientSecretCredential = ClientSecretCredential
    aio.DefaultAzureCredential = DefaultAzureCredential
    aio.ManagedIdentityCredential = ManagedIdentityCredential
    monkeypatch.setitem(sys.modules, "azure.identity.aio", aio)
    created.update(
        {
            "ClientSecretCredential": ClientSecretCredential,
            "DefaultAzureCredential": DefaultAzureCredential,
            "ManagedIdentityCredential": ManagedIdentityCredential,
        }
    )

    az_aio = types.ModuleType("azure.search.documents.aio")

    class SearchClient:  # noqa: N801
        """A stub for azure.search.documents.aio.SearchClient."""

        def __init__(self, *, endpoint: str, index_name: str, credential: Any, **__: Any) -> None:
            self.endpoint = endpoint
            self.index_name = index_name
            self.credential = credential

        async def search(self, *_: Any, **__: Any) -> AsyncIterator[Any]:
            """Return a dummy async iterator that yields nothing."""

            class EmptyAsyncIterator(AsyncIterator[Any]):
                """An empty async iterator for stubbing search results."""

                def __aiter__(self) -> Self:
                    """Return the iterator instance itself."""
                    return self

                async def __anext__(self) -> NoReturn:
                    """Signal the end of the async iteration."""
                    raise StopAsyncIteration

            return EmptyAsyncIterator()

    az_aio.SearchClient = SearchClient
    monkeypatch.setitem(sys.modules, "azure.search.documents.aio", az_aio)
    created["SearchClient"] = SearchClient

    return created


def test_async_builder_client_secret_over_key(monkeypatch: MonkeyPatch) -> None:
    """Verify ClientSecretCredential is used when both key and client-secret exist.

    This test ensures that the async builder's credential priority logic is
    correct. If the configuration contains both an API key and the triplet for
    client-secret auth (tenant_id, client_id, client_secret), the latter should
    be preferred.
    """
    stubs = _install_async_stubs(monkeypatch)
    # Import the builder *after* stubs are installed to ensure it uses the mocks.
    from ingenious.client.azure.builder.search_client_async import (
        AzureSearchAsyncClientBuilder,
    )

    cfg = {
        "endpoint": TEST_ENDPOINT,
        "search_key": TEST_SEARCH_KEY,
        "tenant_id": TEST_TENANT_ID,
        "client_id": TEST_CLIENT_ID,
        "client_secret": TEST_CLIENT_SECRET,
    }
    builder = AzureSearchAsyncClientBuilder.from_config(cfg, index_name=TEST_INDEX_NAME)
    client = builder.build()

    credential_cls = stubs["ClientSecretCredential"]
    assert isinstance(client.credential, credential_cls), (
        f"Expected credential of type '{credential_cls.__name__}', "
        f"but got '{type(client.credential).__name__}'."
    )
