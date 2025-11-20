"""Sync Azure Search builder auth variants (patched to avoid cross-stub isinstance()).

This module contains tests for the synchronous AzureSearchClientBuilder, ensuring it
correctly constructs various Azure Search clients based on different authentication
methods.

It uses pytest's monkeypatch fixture to install in-memory stubs of Azure SDK
modules (e.g., azure.core.credentials, azure.identity), isolating the tests
from actual network calls and dependencies. This allows for focused testing of the
builder's authentication logic.

The primary entry points for testing are the `test_*` functions, each
validating a specific authentication scenario like API key, default credential, MSI,
and client secret.
"""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from ingenious.common.enums import AuthenticationMethod


def _install_sync_azure_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install in-memory stubs for Azure SDK modules.

    This function creates mock versions of necessary Azure modules and classes
    (like credentials and the SearchClient) and patches `sys.modules` to make
    them importable within the test's scope. This avoids requiring the actual
    Azure SDKs to be installed and prevents network calls.

    Args:
        monkeypatch: The pytest fixture for modifying classes, methods, etc.
    """
    # Stub for azure.core.credentials
    core_creds = types.ModuleType("azure.core.credentials")

    class AzureKeyCredential:  # noqa: N801
        """A stub for the AzureKeyCredential class."""

        def __init__(self, key: str) -> None:
            """Initialize with an API key."""
            self.key = key

    core_creds.AzureKeyCredential = AzureKeyCredential
    monkeypatch.setitem(sys.modules, "azure.core.credentials", core_creds)

    # Stub for azure.identity
    id_sync = types.ModuleType("azure.identity")

    class DefaultAzureCredential:  # noqa: N801
        """A stub for the DefaultAzureCredential class."""

        def __init__(self, *_: Any, **__: Any) -> None:
            """Initialize the credential; arguments are ignored."""

    class ManagedIdentityCredential:  # noqa: N801
        """A stub for the ManagedIdentityCredential class."""

        def __init__(self, *_: Any, **__: Any) -> None:
            """Initialize the credential; arguments are ignored."""

    class ClientSecretCredential:  # noqa: N801
        """A stub for the ClientSecretCredential class."""

        def __init__(self, *, tenant_id: str, client_id: str, client_secret: str) -> None:
            """Initialize with service principal credentials."""
            self.tenant_id = tenant_id
            self.client_id = client_id
            self.client_secret = client_secret

    id_sync.DefaultAzureCredential = DefaultAzureCredential
    id_sync.ManagedIdentityCredential = ManagedIdentityCredential
    id_sync.ClientSecretCredential = ClientSecretCredential
    monkeypatch.setitem(sys.modules, "azure.identity", id_sync)

    # Stub for azure.search.documents
    az_search = types.ModuleType("azure.search.documents")

    class SearchClient:  # noqa: N801
        """A stub for the synchronous SearchClient."""

        def __init__(self, *, endpoint: str, index_name: str, credential: Any, **_: Any) -> None:
            """Initialize the mock search client."""
            self.endpoint = endpoint
            self.index_name = index_name
            self.credential = credential

    az_search.SearchClient = SearchClient
    monkeypatch.setitem(sys.modules, "azure.search.documents", az_search)


class _FakeAuth:
    """A test double for an internal authentication configuration object.

    This class mimics the structure of the authentication configuration that the
    AzureSearchClientBuilder expects, allowing tests to inject specific auth
    details without creating a full configuration object.
    """

    def __init__(
        self,
        method: AuthenticationMethod,
        *,
        api_key: str | None = None,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        """Initialize the fake authentication configuration.

        Args:
            method: The authentication method to simulate.
            api_key: The API key for TOKEN authentication.
            tenant_id: The tenant ID for CLIENT_ID_AND_SECRET auth.
            client_id: The client ID for MSI or CLIENT_ID_AND_SECRET auth.
            client_secret: The client secret for CLIENT_ID_AND_SECRET auth.
        """
        self.authentication_method = method
        self.api_key = api_key
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret

    def validate_for_method(self) -> None:
        """Simulate the validation method, performing no action.

        This is a no-op mock method to satisfy the interface expected by the builder.
        """
        return None


def _patch_builder_auth(monkeypatch: pytest.MonkeyPatch, auth: _FakeAuth) -> None:
    """Patch the builder's auth creation method to return a fake config.

    This helper function intercepts the call to create an authentication
    configuration within the AzureSearchClientBuilder and forces it to return
    the provided fake authentication object instead.

    Args:
        monkeypatch: The pytest fixture for modifying classes, methods, etc.
        auth: The fake authentication object to be returned by the patched method.
    """
    from ingenious.client.azure.builder import search_client as mod

    monkeypatch.setattr(
        mod.AzureSearchClientBuilder,
        "_create_auth_config_from_search_config",
        lambda self, _cfg: auth,
        raising=True,
    )


def test_sync_builder_token_uses_key_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that TOKEN auth method uses AzureKeyCredential."""
    _install_sync_azure_stubs(monkeypatch)
    from ingenious.client.azure.builder.search_client import AzureSearchClientBuilder
    from ingenious.common.enums import AuthenticationMethod

    auth = _FakeAuth(AuthenticationMethod.TOKEN, api_key="sekret")
    _patch_builder_auth(monkeypatch, auth)

    cfg = SimpleNamespace(endpoint="https://x.search.windows.net")
    client = AzureSearchClientBuilder(cfg, index_name="idx").build()

    assert getattr(client.credential, "key", None) == "sekret"
    assert type(client.credential).__name__ == "AzureKeyCredential"


def test_sync_builder_default_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that DEFAULT_CREDENTIAL auth method uses DefaultAzureCredential."""
    _install_sync_azure_stubs(monkeypatch)
    from ingenious.client.azure.builder.search_client import AzureSearchClientBuilder
    from ingenious.common.enums import AuthenticationMethod

    auth = _FakeAuth(AuthenticationMethod.DEFAULT_CREDENTIAL)
    _patch_builder_auth(monkeypatch, auth)

    cfg = SimpleNamespace(endpoint="https://x.search.windows.net")
    client = AzureSearchClientBuilder(cfg, index_name="idx").build()

    assert type(client.credential).__name__ == "DefaultAzureCredential"


def test_sync_builder_msi_with_and_without_client_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that MSI auth method uses ManagedIdentityCredential."""
    _install_sync_azure_stubs(monkeypatch)
    from ingenious.client.azure.builder.search_client import AzureSearchClientBuilder
    from ingenious.common.enums import AuthenticationMethod

    cfg = SimpleNamespace(endpoint="https://x.search.windows.net")

    # Test MSI without a specific client ID
    auth1 = _FakeAuth(AuthenticationMethod.MSI, client_id=None)
    _patch_builder_auth(monkeypatch, auth1)
    c1 = AzureSearchClientBuilder(cfg, index_name="idx").build()
    assert type(c1.credential).__name__ == "ManagedIdentityCredential"

    # Test MSI with a specific client ID
    auth2 = _FakeAuth(AuthenticationMethod.MSI, client_id="abc-123")
    _patch_builder_auth(monkeypatch, auth2)
    c2 = AzureSearchClientBuilder(cfg, index_name="idx").build()
    assert type(c2.credential).__name__ == "ManagedIdentityCredential"


def test_sync_builder_client_secret_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that CLIENT_ID_AND_SECRET auth uses ClientSecretCredential."""
    _install_sync_azure_stubs(monkeypatch)
    from ingenious.client.azure.builder.search_client import AzureSearchClientBuilder
    from ingenious.common.enums import AuthenticationMethod

    auth = _FakeAuth(
        AuthenticationMethod.CLIENT_ID_AND_SECRET,
        tenant_id="t",
        client_id="c",
        client_secret="s",
    )
    _patch_builder_auth(monkeypatch, auth)

    # The builder can also construct the endpoint from a service name.
    cfg = SimpleNamespace(service="mysvc", endpoint=None)
    client = AzureSearchClientBuilder(cfg, index_name="idx").build()

    assert client.endpoint == "https://mysvc.search.windows.net"
    assert type(client.credential).__name__ == "ClientSecretCredential"


def test_sync_builder_required_field_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify builder raises ValueError for missing required fields."""
    _install_sync_azure_stubs(monkeypatch)
    from ingenious.client.azure.builder.search_client import AzureSearchClientBuilder
    from ingenious.common.enums import AuthenticationMethod

    # Auth details are patched but not relevant to this test's assertions.
    _patch_builder_auth(monkeypatch, _FakeAuth(AuthenticationMethod.TOKEN, api_key="k"))

    # Test missing index_name.
    good_cfg = SimpleNamespace(endpoint="https://x.search.windows.net")
    with pytest.raises(ValueError, match="Index name is required"):
        AzureSearchClientBuilder(good_cfg, index_name=None).build()  # type: ignore[arg-type]

    # Test missing endpoint/service name.
    bad_cfg = SimpleNamespace(endpoint=None, service=None)
    with pytest.raises(ValueError, match="Endpoint is required"):
        AzureSearchClientBuilder(bad_cfg, index_name="idx").build()
