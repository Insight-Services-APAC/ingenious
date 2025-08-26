"""Provide test fixtures and offline stubs for Azure Search service tests.

This module is a pytest `conftest.py` file. Its primary purpose is to enable
thorough testing of the Azure Search integration (`ingenious.services.azure_search`)
without requiring live Azure or OpenAI services or even having their SDKs installed.

It achieves this by:
- Conditionally installing minimal, import-time stubs for `azure.*` and `openai` modules.
- Providing pytest fixtures that patch client factory functions to return mock objects.
- Supplying dummy configuration objects (`SearchConfig`, etc.) for tests to use.

The key principle is to stub dependencies safely, only when the real packages are
not present, to avoid interfering with environments where they are installed.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from types import SimpleNamespace
from typing import Any, AsyncGenerator, Callable, Dict, Generator, List, Optional, Type
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import SecretStr

# Public model under test
from ingenious.services.azure_search.config import DEFAULT_DAT_PROMPT, SearchConfig


@pytest.fixture(autouse=True)
def _conditionally_clear_semantic_env(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Clear AZURE_SEARCH_SEMANTIC_CONFIG only for the 'missing semantic' test."""
    name = request.node.name.lower()
    if "test_cli_missing_semantic_name_exits_1" in name or "missing_semantic" in name:
        monkeypatch.delenv("AZURE_SEARCH_SEMANTIC_CONFIG", raising=False)


# ----- Lightweight stubs to satisfy imports (no real Azure/OpenAI needed) -----


@pytest.fixture(autouse=True)
def stub_sdks():
    """Stub Azure/OpenAI SDKs so tests run without real dependencies."""
    # ---- azure.core.credentials ----
    mod_core = types.ModuleType("azure.core")
    mod_core_credentials = types.ModuleType("azure.core.credentials")
    mod_core_credentials_async = types.ModuleType("azure.core.credentials_async")

    class AzureKeyCredential:
        def __init__(self, key):
            self.key = key

    class AsyncTokenCredential:  # typing stub/protocol
        ...

    mod_core_credentials.AzureKeyCredential = AzureKeyCredential
    mod_core_credentials_async.AsyncTokenCredential = AsyncTokenCredential
    sys.modules["azure.core"] = mod_core
    sys.modules["azure.core.credentials"] = mod_core_credentials
    sys.modules["azure.core.credentials_async"] = mod_core_credentials_async

    # ---- azure.identity (sync) ----
    mod_identity = types.ModuleType("azure.identity")

    def sync_token_provider(*args, **kwargs):
        return lambda: "sync-token"

    mod_identity.get_bearer_token_provider = sync_token_provider
    sys.modules["azure.identity"] = mod_identity

    # ---- azure.identity.aio (async) ----
    mod_identity_aio = types.ModuleType("azure.identity.aio")

    class DefaultAzureCredential:
        def __init__(self, *a, **k): ...

    class ManagedIdentityCredential:
        def __init__(self, *a, **k): ...

    class ClientSecretCredential:
        def __init__(self, tenant_id=None, client_id=None, client_secret=None):
            self.tenant_id = tenant_id
            self.client_id = client_id
            self.client_secret = client_secret

    def aio_token_provider(_cred, _scope):
        return lambda: "aad-bearer-token"

    mod_identity_aio.DefaultAzureCredential = DefaultAzureCredential
    mod_identity_aio.ManagedIdentityCredential = ManagedIdentityCredential
    mod_identity_aio.ClientSecretCredential = ClientSecretCredential
    mod_identity_aio.get_bearer_token_provider = aio_token_provider
    sys.modules["azure.identity.aio"] = mod_identity_aio

    # ---- azure.search.documents.aio ----
    mod_search = types.ModuleType("azure.search")
    mod_search_documents = types.ModuleType("azure.search.documents")
    mod_search_documents_aio = types.ModuleType("azure.search.documents.aio")

    class FakeSearchClient:
        def __init__(self, *, endpoint, index_name, credential, **kwargs):
            self.endpoint = endpoint
            self.index_name = index_name
            self.credential = credential
            self.kwargs = kwargs

        async def close(self): ...

    mod_search_documents_aio.SearchClient = FakeSearchClient
    sys.modules["azure.search"] = mod_search
    sys.modules["azure.search.documents"] = mod_search_documents
    sys.modules["azure.search.documents.aio"] = mod_search_documents_aio

    # ---- openai ----
    mod_openai = types.ModuleType("openai")

    class FakeAsyncAzureOpenAI:
        def __init__(
            self,
            *,
            azure_endpoint,
            api_version,
            api_key=None,
            azure_ad_token_provider=None,
            **kwargs,
        ):
            self.azure_endpoint = azure_endpoint
            self.api_version = api_version
            self.api_key = api_key
            self.azure_ad_token_provider = azure_ad_token_provider
            self.kwargs = kwargs

        async def close(self): ...

    class FakeAzureOpenAI:
        def __init__(self, *a, **k): ...

    mod_openai.AsyncAzureOpenAI = FakeAsyncAzureOpenAI
    mod_openai.AzureOpenAI = FakeAzureOpenAI
    sys.modules["openai"] = mod_openai

    # ---- pyodbc ----
    mod_pyodbc = types.ModuleType("pyodbc")

    def _connect(*a, **k):
        return object()

    mod_pyodbc.connect = _connect
    sys.modules["pyodbc"] = mod_pyodbc

    # ---- autogen_ext.models.openai ----
    mod_autogen = types.ModuleType("autogen_ext")
    mod_autogen_models = types.ModuleType("autogen_ext.models")
    mod_autogen_models_openai = types.ModuleType("autogen_ext.models.openai")

    class FakeAutoGenClient:
        def __init__(self, *a, **k): ...

    mod_autogen_models_openai.AzureOpenAIChatCompletionClient = FakeAutoGenClient
    sys.modules["autogen_ext"] = mod_autogen
    sys.modules["autogen_ext.models"] = mod_autogen_models
    sys.modules["autogen_ext.models.openai"] = mod_autogen_models_openai

    # ---- azure.storage.blob ----
    mod_blob = types.ModuleType("azure.storage")
    mod_blob_blob = types.ModuleType("azure.storage.blob")

    class BlobClient: ...

    class BlobServiceClient:
        @staticmethod
        def from_connection_string(cs):
            return BlobServiceClient()

    mod_blob_blob.BlobClient = BlobClient
    mod_blob_blob.BlobServiceClient = BlobServiceClient
    sys.modules["azure.storage"] = mod_blob
    sys.modules["azure.storage.blob"] = mod_blob_blob

    yield


class _DummyAsyncAzureOpenAI:
    """A minimal, offline stub for `openai.AsyncAzureOpenAI`."""

    def __init__(self, *a: Any, **kw: Any) -> None:
        """Initialize the dummy client, accepting any arguments."""
        pass

    async def close(self) -> None:
        """Simulate closing the client connection."""
        pass

    class _Embeddings:
        """A dummy for the `embeddings` attribute."""

        async def create(self, *a: Any, **kw: Any) -> SimpleNamespace:
            """Simulate the creation of embeddings, returning a fixed vector."""

            class _D:  # minimal shape
                data = [SimpleNamespace(embedding=[0.0, 0.1])]

            return _D()

    @property
    def embeddings(self) -> _Embeddings:
        """Provide access to the dummy embeddings endpoint."""
        return self._Embeddings()

    class _Chat:
        """A dummy for the `chat` attribute."""

        class _Completions:
            """A dummy for the `completions` attribute."""

            async def create(self, *a: Any, **kw: Any) -> SimpleNamespace:
                """Simulate creating a chat completion, returning a fixed response."""
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="3 4"))]
                )

        @property
        def completions(self) -> _Completions:
            """Provide access to the dummy completions endpoint."""
            return self._Completions()

    @property
    def chat(self) -> _Chat:
        """Provide access to the dummy chat endpoint."""
        return self._Chat()


class _DummySearchClient:
    """A minimal, offline stub for `azure.search.documents.aio.SearchClient`."""

    def __init__(self, *a: Any, **kw: Any) -> None:
        """Initialize the dummy search client, accepting any arguments."""
        pass

    async def search(self, *a: Any, **kw: Any) -> AsyncGenerator[None, None]:
        """Simulate a search query, returning an empty async iterator."""

        async def _aiter() -> AsyncGenerator[None, None]:  # empty iterator
            if False:
                yield None

        return _aiter()

    async def close(self) -> None:
        """Simulate closing the client connection."""
        pass


@pytest.fixture(autouse=True)
def stub_external_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """Ensure azure/openai imports don't fail during tests by stubbing them.

    This fixture creates dummy modules and classes for key Azure and OpenAI
    dependencies and inserts them into `sys.modules`. This allows the application
    code to import them without raising an `ImportError`, which is crucial for
    testing in environments where the full SDKs are not installed.
    """
    # azure.core.credentials.AzureKeyCredential
    sys.modules.setdefault("azure", types.ModuleType("azure"))
    sys.modules.setdefault("azure.core", types.ModuleType("azure.core"))
    creds_mod = types.ModuleType("azure.core.credentials")
    creds_mod.AzureKeyCredential = object
    sys.modules["azure.core.credentials"] = creds_mod

    # azure.search.documents.aio.SearchClient
    sys.modules.setdefault("azure.search", types.ModuleType("azure.search"))
    sys.modules.setdefault(
        "azure.search.documents", types.ModuleType("azure.search.documents")
    )
    aio_mod = types.ModuleType("azure.search.documents.aio")
    aio_mod.SearchClient = _DummySearchClient
    sys.modules["azure.search.documents.aio"] = aio_mod

    # azure.search.documents.models.QueryType / VectorizedQuery
    models_mod = types.ModuleType("azure.search.documents.models")

    class _QueryType:
        SIMPLE = "simple"
        SEMANTIC = "semantic"

    class _VectorizedQuery:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

    models_mod.QueryType = _QueryType
    models_mod.VectorizedQuery = _VectorizedQuery
    sys.modules["azure.search.documents.models"] = models_mod

    # openai.AsyncAzureOpenAI
    openai_mod = types.ModuleType("openai")
    openai_mod.AsyncAzureOpenAI = _DummyAsyncAzureOpenAI
    sys.modules["openai"] = openai_mod

    yield


# ----- Minimal settings objects for the builder (duck-typed) -----


class _Model:
    """A duck-typed representation of OpenAI model configuration settings."""

    def __init__(
        self,
        role: str,
        deployment: str,
        endpoint: str,
        api_key: str,
        api_version: str = "2024-02-15-preview",
    ) -> None:
        """Initialize the model settings object."""
        self.role = role
        self.deployment = deployment
        self.endpoint = endpoint
        self.api_key = api_key
        self.api_version = api_version


class _AzureSearchService:
    """A duck-typed representation of an Azure Search service configuration."""

    def __init__(
        self,
        endpoint: str = "https://example.search.windows.net",
        key: str = "search-key",
        index_name: str = "idx",
        use_semantic_ranking: bool = False,
        semantic_configuration: str = "default",
        top_k_retrieval: int = 5,
        top_n_final: int = 3,
        id_field: str = "id",
        content_field: str = "content",
        vector_field: str = "vector",
    ) -> None:
        """Initialize the search service settings object."""
        self.endpoint = endpoint
        self.key = key
        self.index_name = index_name
        self.use_semantic_ranking = use_semantic_ranking
        self.semantic_configuration = semantic_configuration
        self.top_k_retrieval = top_k_retrieval
        self.top_n_final = top_n_final
        self.id_field = id_field
        self.content_field = content_field
        self.vector_field = vector_field


class _Settings:
    """A duck-typed representation of the main application settings."""

    def __init__(self, enable_answer_generation: bool = False) -> None:
        """Initialize the main settings object."""
        # Two distinct models: embedding + chat
        self.models = [
            _Model("embedding", "emb-dep", "https://aoai.example", "aoai-key"),
            _Model("chat", "chat-dep", "https://aoai.example", "aoai-key"),
        ]
        self.azure_search_services = [_AzureSearchService()]
        # The SearchConfig is immutable; we won't set EAG here (builder doesn't carry it).
        self.enable_answer_generation = (
            enable_answer_generation  # not used by builder; kept for completeness
        )


@pytest.fixture
def settings_disabled() -> _Settings:
    """Provide a settings object with answer generation disabled."""
    return _Settings(enable_answer_generation=False)


@pytest.fixture
def settings_enabled() -> _Settings:
    """Provide a settings object with answer generation enabled."""
    return _Settings(enable_answer_generation=True)


# ----- Dummy pipeline to avoid real work -----


class _DummyPipeline:
    """A stub for the search pipeline to avoid real work in tests."""

    def __init__(self) -> None:
        """Initialize the dummy pipeline state."""
        self.get_answer_called = 0

    async def get_answer(self, query: str) -> Dict[str, Any]:
        """Simulate the pipeline's answer generation, returning a fixed response."""
        self.get_answer_called += 1
        # mirror provider contract
        return {"answer": "A", "source_chunks": [{"id": "1", "content": "x"}]}

    async def close(self) -> None:
        """Simulate closing the pipeline resources."""
        pass


@pytest.fixture
def dummy_pipeline() -> _DummyPipeline:
    """Provide an instance of `_DummyPipeline`."""
    return _DummyPipeline()


@pytest.fixture
def import_provider_with_stubs(
    monkeypatch: pytest.MonkeyPatch, dummy_pipeline: _DummyPipeline
) -> Generator[types.ModuleType, None, None]:
    """Import the provider module after patching its expensive dependencies.

    This ensures that when the provider module is imported, its call to
    `build_search_pipeline` is intercepted and returns a lightweight dummy
    pipeline instead of constructing the real one.
    """
    # Patch azure_search.build_search_pipeline at the provider module binding
    import ingenious.services.azure_search as azroot

    monkeypatch.setattr(
        azroot, "build_search_pipeline", lambda *a, **kw: dummy_pipeline, raising=True
    )

    # Also stub provider's make_async_search_client (to avoid building real clients)
    # We'll import the provider module now and patch its name directly.
    provider_mod = importlib.import_module("ingenious.services.azure_search.provider")
    monkeypatch.setattr(
        provider_mod,
        "build_search_pipeline",
        lambda *a, **kw: dummy_pipeline,
        raising=True,
    )

    class _DummyRerankClient:
        """A dummy client used for reranking."""

        async def close(self) -> None:
            """Simulate closing the client."""
            pass

    monkeypatch.setattr(
        provider_mod,
        "make_async_search_client",
        lambda cfg: _DummyRerankClient(),
        raising=True,
    )

    return provider_mod


# --------------------------------------------------------------------------------------
# Utilities for safe conditional stubbing
# --------------------------------------------------------------------------------------
def _module_exists(name: str) -> bool:
    """Check if a module can be imported without actually importing it."""
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _ensure_pkg(name: str) -> types.ModuleType:
    """Create a namespace package in `sys.modules` only if it does not already exist."""
    if _module_exists(name):
        # Import the real thing so it appears in sys.modules; do not override.
        return importlib.import_module(name)
    mod = types.ModuleType(name)
    # Mark as a namespace package (PEP 420-like)
    mod.__path__ = []
    sys.modules[name] = mod
    return mod


def _ensure_mod(name: str) -> types.ModuleType:
    """Create a module in `sys.modules` only if it does not already exist."""
    if name in sys.modules:
        return sys.modules[name]
    if _module_exists(name):
        return importlib.import_module(name)
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# --------------------------------------------------------------------------------------
# EARLY Azure SDK stubs: must run at import-time, not as a fixture
# --------------------------------------------------------------------------------------
def _install_azure_stubs() -> None:
    """Install minimal Azure stubs ONLY when the real SDK modules are missing.

    This avoids shadowing the real packages when they are installed by checking for
    the existence of key classes before creating stubs. It's a safe way to make
    the codebase runnable for tests without the full `azure-sdk` installed.
    """

    # ----- azure.core.credentials ------------------------------------------------------
    try:
        from azure.core.credentials import AzureKeyCredential  # noqa: F401
    except Exception:
        _ensure_pkg("azure")
        _ensure_pkg("azure.core")
        core_credentials = _ensure_mod("azure.core.credentials")

        if not hasattr(core_credentials, "AzureKeyCredential"):

            class AzureKeyCredential:  # minimal compat
                """A stub for AzureKeyCredential."""

                def __init__(self, key: str) -> None:
                    """Initialize with an API key."""
                    self.key = key

            core_credentials.AzureKeyCredential = AzureKeyCredential

    # ----- azure.core.rest -------------------------------------------------------------
    try:
        from azure.core.rest import HttpResponse  # noqa: F401
    except Exception:
        _ensure_pkg("azure")
        _ensure_pkg("azure.core")
        core_rest = _ensure_mod("azure.core.rest")

        if not hasattr(core_rest, "HttpResponse"):

            class HttpResponse:
                """A stub for HttpResponse."""

                def __init__(
                    self,
                    *,
                    status_code: int = 200,
                    reason: Optional[str] = None,
                    headers: Optional[Dict[str, str]] = None,
                    text: Optional[str] = None,
                ) -> None:
                    """Initialize the dummy response."""
                    self.status_code = status_code
                    self.reason = reason or ""
                    self.headers = headers or {}
                    self._text = text or ""

                def text(self) -> str:  # minimal compat
                    """Return the response body as text."""
                    return self._text

            core_rest.HttpResponse = HttpResponse

    # ----- azure.core.exceptions -------------------------------------------------------
    try:
        from azure.core.exceptions import (  # noqa: F401
            AzureError,
            ClientAuthenticationError,
            HttpResponseError,
            ResourceNotFoundError,
            ServiceRequestError,
            ServiceResponseError,
        )
    except Exception:
        _ensure_pkg("azure")
        _ensure_pkg("azure.core")
        core_exceptions = _ensure_mod("azure.core.exceptions")

        if not hasattr(core_exceptions, "AzureError"):

            class AzureError(Exception):
                """A stub for the base AzureError."""

                def __init__(
                    self, message: Optional[str] = None, **kwargs: Any
                ) -> None:
                    """Initialize the error."""
                    super().__init__(message or "")
                    self.message = message or ""
                    self.kwargs = kwargs

            class HttpResponseError(AzureError):
                """A stub for errors originating from an HTTP response."""

                def __init__(
                    self,
                    message: Optional[str] = None,
                    *,
                    response: Any = None,
                    error: Any = None,
                    status_code: Optional[int] = None,
                    **kwargs: Any,
                ) -> None:
                    """Initialize the HTTP error."""
                    super().__init__(message, **kwargs)
                    self.response = response
                    self.error = error
                    self.status_code = (
                        status_code
                        if status_code is not None
                        else getattr(response, "status_code", None)
                    )

                def __str__(self) -> str:
                    """Return a string representation of the error."""
                    sc = self.status_code
                    return (
                        f"HttpResponseError({sc}): {self.message}"
                        if sc is not None
                        else f"HttpResponseError: {self.message}"
                    )

            class ClientAuthenticationError(HttpResponseError):
                """A stub for authentication errors."""

                ...

            class ResourceNotFoundError(HttpResponseError):
                """A stub for resource not found errors."""

                ...

            class ServiceRequestError(AzureError):
                """A stub for service request errors."""

                ...

            class ServiceResponseError(AzureError):
                """A stub for service response errors."""

                ...

            core_exceptions.AzureError = AzureError
            core_exceptions.HttpResponseError = HttpResponseError
            core_exceptions.ClientAuthenticationError = ClientAuthenticationError
            core_exceptions.ResourceNotFoundError = ResourceNotFoundError
            core_exceptions.ServiceRequestError = ServiceRequestError
            core_exceptions.ServiceResponseError = ServiceResponseError

    # ----- azure.identity (sync) -------------------------------------------------------
    try:
        import azure.identity as _identity  # noqa: F401
    except Exception:
        _ensure_pkg("azure")
        identity = _ensure_mod("azure.identity")

        if not hasattr(identity, "DefaultAzureCredential"):

            class _BaseCredential:
                """Base class for stub credentials."""

                def __init__(self, *a: Any, **k: Any) -> None:
                    """Accept any arguments during initialization."""
                    pass

                def get_token(
                    self, *scopes: str, **kwargs: Any
                ) -> types.SimpleNamespace:
                    """Return a fake token."""
                    return types.SimpleNamespace(token="fake-token", expires_on=0)

            class DefaultAzureCredential(_BaseCredential):
                """Stub for DefaultAzureCredential."""

                ...

            class AzureDeveloperCliCredential(_BaseCredential):
                """Stub for AzureDeveloperCliCredential."""

                ...

            class ManagedIdentityCredential(_BaseCredential):
                """Stub for ManagedIdentityCredential."""

                ...

            class VisualStudioCodeCredential(_BaseCredential):
                """Stub for VisualStudioCodeCredential."""

                ...

            class ClientSecretCredential(_BaseCredential):
                """Stub for ClientSecretCredential."""

                def __init__(
                    self,
                    tenant_id: str,
                    client_id: str,
                    client_secret: str,
                    **kwargs: Any,
                ) -> None:
                    """Initialize with required credentials."""
                    super().__init__(tenant_id, client_id, client_secret, **kwargs)

            class ClientCertificateCredential(_BaseCredential):
                """Stub for ClientCertificateCredential."""

                def __init__(
                    self,
                    tenant_id: str,
                    client_id: str,
                    certificate_path: Optional[str] = None,
                    **kwargs: Any,
                ) -> None:
                    """Initialize with required credentials."""
                    super().__init__(tenant_id, client_id, certificate_path, **kwargs)

            class EnvironmentCredential(_BaseCredential):
                """Stub for EnvironmentCredential."""

                ...

            class InteractiveBrowserCredential(_BaseCredential):
                """Stub for InteractiveBrowserCredential."""

                ...

            class DeviceCodeCredential(_BaseCredential):
                """Stub for DeviceCodeCredential."""

                ...

            class ChainedTokenCredential(_BaseCredential):
                """Stub for ChainedTokenCredential."""

                def __init__(self, *credentials: Any) -> None:
                    """Initialize with a sequence of credentials."""
                    self._creds = credentials

                def get_token(
                    self, *scopes: str, **kwargs: Any
                ) -> types.SimpleNamespace:
                    """Attempt to get a token from each credential in the chain."""
                    for c in self._creds:
                        tok = getattr(c, "get_token", lambda *a, **k: None)(
                            *scopes, **kwargs
                        )
                        if tok:
                            return tok
                    return super().get_token(*scopes, **kwargs)

            def get_bearer_token_provider(
                credential: Any, scope: Any
            ) -> Callable[..., str]:
                """Return a fake bearer token provider function."""

                def _provider(*a: Any, **k: Any) -> str:
                    """Return a static fake token."""
                    return "fake-token"

                return _provider

            identity.DefaultAzureCredential = DefaultAzureCredential
            identity.AzureDeveloperCliCredential = AzureDeveloperCliCredential
            identity.ManagedIdentityCredential = ManagedIdentityCredential
            identity.VisualStudioCodeCredential = VisualStudioCodeCredential
            identity.ClientSecretCredential = ClientSecretCredential
            identity.ClientCertificateCredential = ClientCertificateCredential
            identity.EnvironmentCredential = EnvironmentCredential
            identity.InteractiveBrowserCredential = InteractiveBrowserCredential
            identity.DeviceCodeCredential = DeviceCodeCredential
            identity.ChainedTokenCredential = ChainedTokenCredential
            identity.get_bearer_token_provider = get_bearer_token_provider

    # ----- azure.identity.aio (mirror) -------------------------------------------------
    try:
        import azure.identity.aio as _identity_aio  # noqa: F401
    except Exception:
        identity = _ensure_mod("azure.identity")
        identity_aio = _ensure_mod("azure.identity.aio")
        # Mirror the sync credentials if aio missing
        for name in (
            "DefaultAzureCredential",
            "AzureDeveloperCliCredential",
            "ManagedIdentityCredential",
            "VisualStudioCodeCredential",
            "ClientSecretCredential",
            "ClientCertificateCredential",
            "EnvironmentCredential",
            "InteractiveBrowserCredential",
            "DeviceCodeCredential",
            "ChainedTokenCredential",
            "get_bearer_token_provider",
        ):
            if not hasattr(identity_aio, name) and hasattr(identity, name):
                setattr(identity_aio, name, getattr(identity, name))

    # ----- azure.keyvault.secrets (sync + aio) ----------------------------------------
    try:
        from azure.keyvault.secrets import SecretClient as _KVSecretClient  # noqa: F401
    except Exception:
        _ensure_pkg("azure")
        _ensure_pkg("azure.keyvault")
        secrets_mod = _ensure_mod("azure.keyvault.secrets")

        if not hasattr(secrets_mod, "SecretClient"):

            class _KeyVaultSecret:
                """A stub for a Key Vault secret."""

                def __init__(self, name: str, value: str) -> None:
                    """Initialize the secret."""
                    self.name = name
                    self.value = value
                    self.properties = types.SimpleNamespace(enabled=True)

            class SecretClient:  # minimal KV Secrets client
                """A stub for the synchronous Key Vault SecretClient."""

                def __init__(
                    self, vault_url: str, credential: Any, **kwargs: Any
                ) -> None:
                    """Initialize the client with a vault URL and credential."""
                    self.vault_url = vault_url
                    self.credential = credential
                    self._store: Dict[str, _KeyVaultSecret] = {}

                def get_secret(self, name: str, **kwargs: Any) -> _KeyVaultSecret:
                    """Retrieve a secret from the in-memory store."""
                    from azure.core.exceptions import ResourceNotFoundError

                    if name in self._store:
                        return self._store[name]
                    raise ResourceNotFoundError(f"Secret '{name}' not found")

                def set_secret(
                    self, name: str, value: str, **kwargs: Any
                ) -> _KeyVaultSecret:
                    """Set a secret in the in-memory store."""
                    s = _KeyVaultSecret(name, value)
                    self._store[name] = s
                    return s

            secrets_mod.SecretClient = SecretClient
            secrets_mod.KeyVaultSecret = _KeyVaultSecret

    try:
        from azure.keyvault.secrets.aio import (
            SecretClient as _AioKVSecretClient,  # noqa: F401
        )
    except Exception:
        secrets_mod = _ensure_mod("azure.keyvault.secrets")
        secrets_aio = _ensure_mod("azure.keyvault.secrets.aio")

        if not hasattr(secrets_aio, "SecretClient"):

            class _AioSecretClient:
                """A stub for the asynchronous Key Vault SecretClient."""

                def __init__(
                    self, vault_url: str, credential: Any, **kwargs: Any
                ) -> None:
                    """Initialize the async client, wrapping a sync version."""
                    self._sync: Any = secrets_mod.SecretClient(
                        vault_url, credential, **kwargs
                    )

                async def get_secret(self, name: str, **kwargs: Any) -> Any:
                    """Asynchronously retrieve a secret."""
                    return self._sync.get_secret(name, **kwargs)

                async def set_secret(self, name: str, value: str, **kwargs: Any) -> Any:
                    """Asynchronously set a secret."""
                    return self._sync.set_secret(name, value, **kwargs)

                async def close(self) -> None:
                    """Close the client."""
                    pass

            secrets_aio.SecretClient = _AioSecretClient

    # ----- azure.search.documents (sync) ----------------------------------------------
    try:
        from azure.search.documents import (
            SearchClient as _SyncSearchClient,  # noqa: F401
        )
    except Exception:
        _ensure_pkg("azure")
        _ensure_pkg("azure.search")
        docs_sync = _ensure_mod("azure.search.documents")
        if not hasattr(docs_sync, "SearchClient"):

            class _SyncSearchClient:
                """A stub for the synchronous SearchClient."""

                def __init__(
                    self,
                    endpoint: Optional[str] = None,
                    index_name: Optional[str] = None,
                    credential: Any = None,
                    **kwargs: Any,
                ) -> None:
                    """Initialize the client."""
                    self.endpoint = endpoint
                    self.index_name = index_name
                    self.credential = credential

                def search(self, *args: Any, **kwargs: Any) -> List[Any]:
                    """Simulate a search, returning an empty list."""
                    # Return an empty iterable for minimal compatibility
                    return []

                def close(self) -> None:
                    """Close the client."""
                    pass

            _SyncSearchClient.__module__ = "azure.search.documents"
            docs_sync.SearchClient = _SyncSearchClient

    # ----- azure.search.documents.aio (async) -----------------------------------------
    try:
        from azure.search.documents.aio import (
            SearchClient as _AioSearchClient,  # noqa: F401
        )
    except Exception:
        _ensure_pkg("azure")
        _ensure_pkg("azure.search")
        _ensure_mod("azure.search.documents")
        docs_aio = _ensure_mod("azure.search.documents.aio")

        if not hasattr(docs_aio, "SearchClient"):

            class _AioSearchClient:
                """A stub for the asynchronous SearchClient."""

                def __init__(
                    self,
                    endpoint: Optional[str] = None,
                    index_name: Optional[str] = None,
                    credential: Any = None,
                    **kwargs: Any,
                ) -> None:
                    """Initialize the client."""
                    self.endpoint = endpoint
                    self.index_name = index_name
                    self.credential = credential

                async def search(
                    self, *args: Any, **kwargs: Any
                ) -> AsyncGenerator[Dict[str, Any], None]:
                    """Simulate a search, returning an empty async iterator."""

                    async def _aiter() -> AsyncGenerator[Dict[str, Any], None]:
                        if False:  # pragma: no cover
                            yield {}

                    return _aiter()

                async def close(self) -> None:
                    """Close the client."""
                    pass

            _AioSearchClient.__module__ = "azure.search.documents.aio"
            docs_aio.SearchClient = _AioSearchClient

    # ----- azure.search.documents.models ----------------------------------------------
    try:
        from azure.search.documents.models import (  # noqa: F401
            QueryType,
            VectorizedQuery,
        )
    except Exception:
        _ensure_pkg("azure")
        _ensure_pkg("azure.search")
        _ensure_mod("azure.search.documents")
        docs_models = _ensure_mod("azure.search.documents.models")

        if not hasattr(docs_models, "QueryType"):

            class _QueryType:
                """A stub for `QueryType` enum."""

                SIMPLE = 1
                SEMANTIC = 2

            class _VectorizedQuery:
                """A stub for `VectorizedQuery`."""

                def __init__(
                    self,
                    *,
                    vector: Any,
                    k_nearest_neighbors: int,
                    fields: str,
                    exhaustive: bool = True,
                ) -> None:
                    """Initialize the vectorized query."""
                    self.vector = vector
                    self.k_nearest_neighbors = k_nearest_neighbors
                    self.fields = fields
                    self.exhaustive = exhaustive

            docs_models.QueryType = _QueryType
            docs_models.VectorizedQuery = _VectorizedQuery


# Install stubs (safe: only where needed)
_install_azure_stubs()


# --------------------------------------------------------------------------------------
# Other third-party placeholders used by tests
# --------------------------------------------------------------------------------------
def _ensure_stub_module(name: str, attrs: Dict[str, Any]) -> None:
    """Make a stub importable module so patches on it won't fail if it's not installed."""
    if name not in sys.modules:
        mod = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        sys.modules[name] = mod


# Allow patch('chromadb.PersistentClient', ...) even if chromadb isn't installed.
_ensure_stub_module("chromadb", {"PersistentClient": MagicMock()})


# --------------------------------------------------------------------------------------
# Test helpers and fixtures
# --------------------------------------------------------------------------------------
class AsyncIter:
    """A helper class to create an async iterator from a list of items."""

    def __init__(self, items: List[Any]) -> None:
        """Initialize with a list of items to iterate over."""
        self._items = items

    async def __aiter__(self) -> AsyncGenerator[Any, None]:
        """Return an async generator for the items."""
        for item in self._items:
            yield item


class DummyQueryType:
    """A stub for `azure.search.documents.models.QueryType` used in tests."""

    SIMPLE = "simple"
    SEMANTIC = "semantic"


class DummyVectorizedQuery:
    """A stub for `azure.search.documents.models.VectorizedQuery` used in tests."""

    def __init__(
        self,
        *,
        vector: List[float],
        k_nearest_neighbors: int,
        fields: str,
        exhaustive: bool = True,
    ) -> None:
        """Initialize the dummy vectorized query."""
        self.vector = vector
        self.k_nearest_neighbors = k_nearest_neighbors
        self.fields = fields
        self.exhaustive = exhaustive


@pytest.fixture(autouse=True, scope="session")
def _preseed_tool_factory_patch_targets() -> None:
    """Ensure patch targets exist on the `tool_factory` module before tests run.

    Some tests patch attributes on `tool_factory` that may not exist in the
    production code depending on dependencies. This fixture pre-creates harmless
    placeholders so `unittest.mock.patch` can successfully replace them
    without causing `AttributeError`.
    """
    import importlib

    tf = importlib.import_module(
        "ingenious.services.chat_services.multi_agent.tool_factory"
    )

    if not hasattr(tf, "AzureSearchProvider"):
        tf.AzureSearchProvider = object  # type: ignore[attr-defined]

    if not hasattr(tf, "get_config"):

        def _placeholder_get_config() -> None:
            """A placeholder function that raises if called."""
            raise RuntimeError("get_config placeholder: tests must patch this symbol.")

        tf.get_config = _placeholder_get_config  # type: ignore[attr-defined]


@pytest.fixture
def mock_search_config(config: SearchConfig) -> SearchConfig:
    """Alias the suite's existing 'config' fixture to the name these tests expect."""
    return config


@pytest.fixture
def mock_ingenious_settings() -> SimpleNamespace:
    """Provide a minimal, duck-typed settings object for tests."""
    svc = SimpleNamespace(
        endpoint="https://unit.search.windows.net",
        key="unit-key",
        index_name="unit-index",
    )
    return SimpleNamespace(azure_search_services=[svc])


@pytest.fixture
def mock_async_openai_client() -> SimpleNamespace:
    """Provide a stub for an `AsyncAzureOpenAI`-like client."""
    client = SimpleNamespace()
    client.chat = SimpleNamespace()
    client.chat_completions = SimpleNamespace()  # tolerate alt path if needed
    client.chat.completions = SimpleNamespace()
    client.chat.completions.create = AsyncMock()
    return client


@pytest.fixture(autouse=True)
def patch_external_sdks(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Patch external SDK symbols and client factories for offline testing.

    This fixture performs several critical patches:
    - Replaces Azure Search model classes (`QueryType`, `VectorizedQuery`) with dummies.
    - Replaces client factory functions (`make_async_search_client`, `make_async_openai_client`)
      to return shared `AsyncMock` instances.
    - Ensures these patches are applied across various modules that might import them.
    """
    # Make asyncio errors clearer
    monkeypatch.setenv("PYTHONASYNCIODEBUG", "0")

    # Patch model symbols where modules import them
    monkeypatch.setitem(globals(), "DummyQueryType", DummyQueryType)
    monkeypatch.setitem(globals(), "DummyVectorizedQuery", DummyVectorizedQuery)

    # Retrieval module uses these names at import time
    for target in [
        "ingenious.services.azure_search.components.retrieval.QueryType",
        "ingenious.services.azure_search.components.pipeline.QueryType",
    ]:
        try:
            monkeypatch.setattr(target, DummyQueryType, raising=False)
        except Exception:
            pass

    try:
        monkeypatch.setattr(
            "ingenious.services.azure_search.components.retrieval.VectorizedQuery",
            DummyVectorizedQuery,
            raising=False,
        )
    except Exception:
        pass

    # Create shared async OpenAI mock with embeddings & chat
    openai_client = AsyncMock(name="AsyncAzureOpenAI")
    openai_client.embeddings.create = AsyncMock(
        return_value=SimpleNamespace(data=[SimpleNamespace(embedding=[0.01] * 3)])
    )
    openai_client.chat.completions.create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="3 4"))]
        )
    )

    # Create shared search client mock with .search() async iterator and .close()
    search_client = AsyncMock(name="SearchClient")
    search_client.search = AsyncMock(return_value=AsyncIter([]))
    search_client.close = AsyncMock()

    # Patch factory functions to return our shared clients
    monkeypatch.setattr(
        "ingenious.services.azure_search.client_init.make_async_openai_client",
        lambda cfg: openai_client,
        raising=False,
    )
    monkeypatch.setattr(
        "ingenious.services.azure_search.client_init.make_async_search_client",
        lambda cfg: search_client,
        raising=False,
    )

    # Components import factories dynamically; also patch potential direct paths
    for mod in [
        "ingenious.services.azure_search.components.retrieval",
        "ingenious.services.azure_search.components.fusion",
        "ingenious.services.azure_search.components.generation",
        "ingenious.services.azure_search.pipeline",
    ]:
        try:
            monkeypatch.setattr(
                f"{mod}.make_async_openai_client",
                lambda cfg: openai_client,
                raising=False,
            )
        except Exception:
            pass
        try:
            monkeypatch.setattr(
                f"{mod}.make_async_search_client",
                lambda cfg: search_client,
                raising=False,
            )
        except Exception:
            pass

    # Expose to tests that need them
    yield


# --- Core config fixtures -----------------------------------------------------
@pytest.fixture
def config() -> SearchConfig:
    """Provide a standard, valid `SearchConfig` instance for most tests."""
    return SearchConfig(
        search_endpoint="https://unit-search.windows.net",
        search_key=SecretStr("search_key"),
        search_index_name="unit-index",
        semantic_configuration_name="sem-config",
        openai_endpoint="https://unit-openai.azure.com",
        openai_key=SecretStr("openai_key"),
        openai_version="2024-02-01",
        embedding_deployment_name="embed-deploy",
        generation_deployment_name="chat-deploy",
        top_k_retrieval=10,
        use_semantic_ranking=True,
        top_n_final=3,
        id_field="id",
        content_field="content",
        vector_field="vector",
        dat_prompt=DEFAULT_DAT_PROMPT,
    )


@pytest.fixture
def config_no_semantic(config: SearchConfig) -> SearchConfig:
    """Provide a `SearchConfig` variant with semantic ranking disabled."""
    data: Dict[str, Any] = config.model_dump(exclude={"search_key", "openai_key"})
    data["use_semantic_ranking"] = False
    data["semantic_configuration_name"] = None
    data["search_key"] = config.search_key
    data["openai_key"] = config.openai_key
    return SearchConfig(**data)


# Utility fixtures re-exposed for tests that want them
@pytest.fixture
def async_iter() -> Type[AsyncIter]:
    """Return the `AsyncIter` helper class, used for creating async iterators."""
    return AsyncIter
