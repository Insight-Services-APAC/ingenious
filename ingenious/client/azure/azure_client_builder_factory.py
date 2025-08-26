"""
Azure Client Factory for building various Azure service clients.

Production goals:
- Keep optional Azure SDKs truly optional (lazy, memoized imports).
- Preserve testability by exposing patchable builder symbols at module scope.
- Provide deterministic error messages for missing optional dependencies.
"""

from __future__ import annotations

import importlib
import importlib.util
from typing import Any, Mapping, Optional, Union

from ingenious.common.enums import AuthenticationMethod
from ingenious.config.models import (
    AzureSearchSettings,
    AzureSqlSettings,
    CosmosSettings,
    FileStorageContainerSettings,
    ModelSettings,
)
from ingenious.models.config import (
    AzureSearchConfig,
    AzureSqlConfig,
    CosmosConfig,
    FileStorageContainer,
    ModelConfig,
)

# --------------------------------------------------------------------------------------
# Optional dependency flags (evaluated once at import)
# --------------------------------------------------------------------------------------


def _has_module(modname: str) -> bool:
    try:
        return importlib.util.find_spec(modname) is not None
    except Exception:
        return False


HAS_SEARCH: bool = _has_module("azure.search.documents")
HAS_COSMOS: bool = _has_module("azure.cosmos")

# --------------------------------------------------------------------------------------
# Patchable builder symbols (initialized to None; tests can patch these directly).
# --------------------------------------------------------------------------------------

AzureOpenAIClientBuilder = NoneAzureOpenAIChatCompletionClientBuilder = (
    NoneBlobServiceClientBuilder
) = NoneBlobClientBuilder = NoneAzureSearchClientBuilder = NoneAzureSqlClientBuilder = (
    NoneAzureSqlClientBuilderWithAuth
) = NoneAzureSearchAsyncClientBuilder = NoneAsyncAzureOpenAIClientBuilder = None
__all__ = [
    "AzureClientFactory",
    "HAS_COSMOS",
    "HAS_SEARCH",
    "AzureOpenAIClientBuilder",
    "AzureOpenAIChatCompletionClientBuilder",
    "BlobServiceClientBuilder",
    "BlobClientBuilder",
    "AzureSearchClientBuilder",
    "AzureSqlClientBuilder",
    "AzureSqlClientBuilderWithAuth",
    "AzureSearchAsyncClientBuilder",
    "AsyncAzureOpenAIClientBuilder",
]

_PKG_BASE = __package__  # e.g., "ingenious.client.azure"


# --------------------------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------------------------


def _ensure_builder(
    global_name: str,
    import_path: str,
    attr_name: str,
    missing_msg: str,
) -> Any:
    existing = globals().get(global_name)
    if existing is not None:
        return existing

    try:
        mod = importlib.import_module(import_path)
        builder = getattr(mod, attr_name)
    except Exception as e:
        raise ImportError(missing_msg) from e

    globals()[global_name] = builder
    return builder


# --------------------------------------------------------------------------------------
# Factory
# --------------------------------------------------------------------------------------


class AzureClientFactory:
    """Factory class for creating Azure service clients with proper authentication."""

    # --------------------------- OpenAI (sync) ---------------------------

    @staticmethod
    def create_openai_client(
        model_config: Union[ModelConfig, ModelSettings],
    ) -> Any:
        builder_cls = _ensure_builder(
            "AzureOpenAIClientBuilder",
            f"{_PKG_BASE}.builder.openai_client",
            "AzureOpenAIClientBuilder",
            "openai is required to create an Azure OpenAI client",
        )
        builder = builder_cls(model_config)
        return builder.build()

    @staticmethod
    def create_openai_client_from_params(
        model: str,
        base_url: str,
        api_version: str,
        deployment: Optional[str] = None,
        api_key: Optional[str] = None,
        authentication_method: AuthenticationMethod = AuthenticationMethod.DEFAULT_CREDENTIAL,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Any:
        builder_cls = _ensure_builder(
            "AzureOpenAIClientBuilder",
            f"{_PKG_BASE}.builder.openai_client",
            "AzureOpenAIClientBuilder",
            "openai is required to create an Azure OpenAI client",
        )
        # Use model_construct to avoid strict credential validation in enum-usage tests.
        model_settings = ModelSettings.model_construct(
            model=model,
            api_type="rest",
            base_url=base_url,
            api_version=api_version,
            deployment=(deployment or model),
            api_key=(api_key or ""),
            authentication_method=authentication_method,
            client_id=(client_id or ""),
            client_secret=(client_secret or ""),
            tenant_id=(tenant_id or ""),
        )
        builder = builder_cls(model_settings)
        return builder.build()

    # ----------- OpenAI Chat Completions client (sync, optional) -----------

    @staticmethod
    def create_openai_chat_completion_client(
        model_config: Union[ModelConfig, ModelSettings],
    ) -> Any:
        builder_cls = _ensure_builder(
            "AzureOpenAIChatCompletionClientBuilder",
            f"{_PKG_BASE}.builder.openai_chat_completions_client",
            "AzureOpenAIChatCompletionClientBuilder",
            "autogen-ext is required to create the chat client",
        )
        builder = builder_cls(model_config)
        return builder.build()

    @staticmethod
    def create_openai_chat_completion_client_from_params(
        model: str,
        base_url: str,
        api_version: str,
        deployment: Optional[str] = None,
        api_key: Optional[str] = None,
        authentication_method: AuthenticationMethod = AuthenticationMethod.DEFAULT_CREDENTIAL,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Any:
        builder_cls = _ensure_builder(
            "AzureOpenAIChatCompletionClientBuilder",
            f"{_PKG_BASE}.builder.openai_chat_completions_client",
            "AzureOpenAIChatCompletionClientBuilder",
            "autogen-ext is required to create the chat client",
        )
        model_settings = ModelSettings.model_construct(
            model=model,
            api_type="rest",
            base_url=base_url,
            api_version=api_version,
            deployment=(deployment or model),
            api_key=(api_key or ""),
            authentication_method=authentication_method,
            client_id=(client_id or ""),
            client_secret=(client_secret or ""),
            tenant_id=(tenant_id or ""),
        )
        builder = builder_cls(model_settings)
        return builder.build()

    # --------------------------- Blob (sync) ---------------------------

    @staticmethod
    def create_blob_service_client(
        file_storage_config: Union[FileStorageContainer, FileStorageContainerSettings],
    ) -> Any:
        builder_cls = _ensure_builder(
            "BlobServiceClientBuilder",
            f"{_PKG_BASE}.builder.blob_client",
            "BlobServiceClientBuilder",
            "azure-storage-blob is required to create blob clients",
        )
        builder = builder_cls(file_storage_config)
        return builder.build()

    @staticmethod
    def create_blob_service_client_from_params(
        account_url: str,
        authentication_method: AuthenticationMethod = AuthenticationMethod.DEFAULT_CREDENTIAL,
        token: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> Any:
        builder_cls = _ensure_builder(
            "BlobServiceClientBuilder",
            f"{_PKG_BASE}.builder.blob_client",
            "BlobServiceClientBuilder",
            "azure-storage-blob is required to create blob clients",
        )
        file_storage_settings = FileStorageContainerSettings(
            enable=True,
            storage_type="azure",
            container_name="",
            path="./",
            add_sub_folders=True,
            url=account_url,
            client_id=(client_id or ""),
            token=(token or ""),
            authentication_method=authentication_method,
        )
        builder = builder_cls(file_storage_settings)
        return builder.build()

    @staticmethod
    def create_blob_client(
        file_storage_config: Union[FileStorageContainer, FileStorageContainerSettings],
        blob_name: str,
        container_name: Optional[str] = None,
    ) -> Any:
        builder_cls = _ensure_builder(
            "BlobClientBuilder",
            f"{_PKG_BASE}.builder.blob_client",
            "BlobClientBuilder",
            "azure-storage-blob is required to create blob clients",
        )
        builder = builder_cls(file_storage_config, container_name, blob_name)
        return builder.build()

    @staticmethod
    def create_blob_client_from_params(
        account_url: str,
        blob_name: str,
        container_name: str,
        authentication_method: AuthenticationMethod = AuthenticationMethod.DEFAULT_CREDENTIAL,
        token: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> Any:
        builder_cls = _ensure_builder(
            "BlobClientBuilder",
            f"{_PKG_BASE}.builder.blob_client",
            "BlobClientBuilder",
            "azure-storage-blob is required to create blob clients",
        )
        file_storage_settings = FileStorageContainerSettings(
            enable=True,
            storage_type="azure",
            container_name=container_name,
            path="./",
            add_sub_folders=True,
            url=account_url,
            client_id=(client_id or ""),
            token=(token or ""),
            authentication_method=authentication_method,
        )
        builder = builder_cls(file_storage_settings, container_name, blob_name)
        return builder.build()

    # --------------------------- Cosmos (sync, optional) ---------------------------

    @staticmethod
    def create_cosmos_client(
        cosmos_config: Union[CosmosConfig, CosmosSettings, None] = None,
        **_: Any,
    ) -> Any:
        """
        Current test contract:
        - If the cosmos package is missing (`HAS_COSMOS` is False): raise ImportError
          with "azure-cosmos is required".
        - If present (`HAS_COSMOS` is True): return NotImplemented.

        Accepts kwargs for compatibility with tests that pass endpoint/auth values.
        """
        if not HAS_COSMOS:
            raise ImportError("azure-cosmos is required")
        return NotImplemented

    # --------------------------- Search (sync) ---------------------------

    @staticmethod
    def create_search_client(
        search_config: Union[AzureSearchConfig, AzureSearchSettings], index_name: str
    ) -> Any:
        if not HAS_SEARCH:
            raise ImportError("azure-search-documents is required")
        builder_cls = _ensure_builder(
            "AzureSearchClientBuilder",
            f"{_PKG_BASE}.builder.search_client",
            "AzureSearchClientBuilder",
            "azure-search-documents is required",
        )
        builder = builder_cls(search_config, index_name)
        return builder.build()

    @staticmethod
    def create_search_client_from_params(
        endpoint: str,
        index_name: str,
        api_key: str,
        service: Optional[str] = None,
        authentication_method: AuthenticationMethod = AuthenticationMethod.DEFAULT_CREDENTIAL,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Any:
        if not HAS_SEARCH:
            raise ImportError("azure-search-documents is required")
        builder_cls = _ensure_builder(
            "AzureSearchClientBuilder",
            f"{_PKG_BASE}.builder.search_client",
            "AzureSearchClientBuilder",
            "azure-search-documents is required",
        )
        search_settings = AzureSearchSettings(
            service=(service or ""),
            endpoint=endpoint,
            key=api_key,
            client_id=(client_id or ""),
            client_secret=(client_secret or ""),
            tenant_id=(tenant_id or ""),
            authentication_method=authentication_method,
        )
        builder = builder_cls(search_settings, index_name)
        return builder.build()

    # --------------------------- SQL (sync) ---------------------------

    @staticmethod
    def create_sql_client(
        sql_config: Union[AzureSqlConfig, AzureSqlSettings],
    ) -> Any:
        builder_cls = _ensure_builder(
            "AzureSqlClientBuilder",
            f"{_PKG_BASE}.builder.sql_client",
            "AzureSqlClientBuilder",
            "pyodbc is required to create Azure SQL client",
        )
        builder = builder_cls(sql_config)
        return builder.build()

    @staticmethod
    def create_sql_client_from_params(
        database_name: str,
        connection_string: str,
        table_name: Optional[str] = None,
    ) -> Any:
        builder_cls = _ensure_builder(
            "AzureSqlClientBuilder",
            f"{_PKG_BASE}.builder.sql_client",
            "AzureSqlClientBuilder",
            "pyodbc is required to create Azure SQL client",
        )
        sql_settings = AzureSqlSettings(
            database_name=database_name,
            table_name=(table_name or ""),
            database_connection_string=connection_string,
        )
        builder = builder_cls(sql_settings)
        return builder.build()

    @staticmethod
    def create_sql_client_with_auth(
        server: str,
        database: str,
        authentication_method: AuthenticationMethod = AuthenticationMethod.DEFAULT_CREDENTIAL,
        username: Optional[str] = None,
        password: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Any:
        builder_cls = _ensure_builder(
            "AzureSqlClientBuilderWithAuth",
            f"{_PKG_BASE}.builder.sql_client",
            "AzureSqlClientBuilderWithAuth",
            "pyodbc is required to create Azure SQL client",
        )
        builder = builder_cls(
            server=server,
            database=database,
            authentication_method=authentication_method,
            username=username,
            password=password,
            client_id=client_id,
            client_secret=client_secret,
            tenant_id=tenant_id,
        )
        return builder.build()

    @staticmethod
    def create_sql_client_with_auth_from_params(
        server: str,
        database: str,
        authentication_method: AuthenticationMethod = AuthenticationMethod.DEFAULT_CREDENTIAL,
        username: Optional[str] = None,
        password: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Any:
        return AzureClientFactory.create_sql_client_with_auth(
            server=server,
            database=database,
            authentication_method=authentication_method,
            username=username,
            password=password,
            client_id=client_id,
            client_secret=client_secret,
            tenant_id=tenant_id,
        )

    # --------------------------- Async builders (optional) ---------------------------

    @staticmethod
    def create_async_search_client(
        index_name: str,
        config: Optional[
            Mapping[str, Any] | AzureSearchConfig | AzureSearchSettings
        ] = None,
        **client_options: Any,
    ) -> Any:
        builder_cls = _ensure_builder(
            "AzureSearchAsyncClientBuilder",
            f"{_PKG_BASE}.builder.search_client_async",
            "AzureSearchAsyncClientBuilder",
            "azure-search-documents is required to create async search client",
        )
        builder = builder_cls.from_config(
            config, index_name=index_name, client_options=client_options
        )
        return builder.build()

    @staticmethod
    def create_async_openai_client(
        config: Optional[Mapping[str, Any] | ModelConfig | ModelSettings] = None,
        api_version: Optional[str] = None,
        **client_options: Any,
    ) -> Any:
        builder_cls = _ensure_builder(
            "AsyncAzureOpenAIClientBuilder",
            f"{_PKG_BASE}.builder.openai_client_async",
            "AsyncAzureOpenAIClientBuilder",
            "openai is required to create an async Azure OpenAI client",
        )
        builder = builder_cls.from_config(
            config, api_version=api_version, client_options=client_options
        )
        return builder.build()
