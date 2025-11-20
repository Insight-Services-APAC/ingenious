"""Pydantic models for configuration settings.

This module contains all the BaseModel classes that define
the structure and validation for different configuration sections.
"""

from pydantic import (
    BaseModel,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from ingenious.common.enums import AuthenticationMethod


class ChatHistorySettings(BaseModel):
    """Configuration for chat history storage.

    Supports SQLite (local), Azure SQL (cloud), and Azure Cosmos DB (cloud).
    For local development, SQLite is recommended. For production, use Azure
    SQL or Cosmos DB.
    """

    database_type: str = Field(
        "sqlite",
        description=("Type of database: 'sqlite' for local, 'azuresql' or 'cosmos' for cloud"),
    )
    database_path: str = Field(
        "./tmp/high_level_logs.db",
        description="File path for SQLite database (ignored for Azure SQL)",
    )
    database_connection_string: str = Field(
        "", description="Connection string for Azure SQL (leave empty for SQLite)"
    )
    database_name: str = Field("", description="Database name for Azure SQL (ignored for SQLite)")
    memory_path: str = Field("./tmp", description="Path for memory storage and temporary files")


class ModelSettings(BaseModel):
    """Configuration for AI models.

    Defines which AI models to use and how to connect to them.
    Supports Azure OpenAI, OpenAI, and other compatible endpoints.
    Contains Azure authentication configuration fields.
    """

    model: str = Field(..., description="Model name (e.g., 'gpt-4.1-nano', 'gpt-3.5-turbo')")
    api_type: str = Field("rest", description="API type: 'rest' for HTTP APIs")
    api_version: str = Field("2023-03-15-preview", description="API version for Azure OpenAI")
    deployment: str = Field("", description="Azure OpenAI deployment name (optional)")
    base_url: str = Field("", description="Base URL for the API endpoint")

    # Azure authentication fields
    authentication_method: AuthenticationMethod = Field(
        default=AuthenticationMethod.TOKEN, description="Authentication method for Azure services"
    )
    api_key: str = Field("", description="API key for token-based authentication")
    client_id: str = Field("", description="Azure client ID for service principal or MSI")
    client_secret: str = Field(
        "", description="Azure client secret for service principal authentication"
    )
    tenant_id: str = Field("", description="Azure tenant ID for service principal authentication")
    endpoint: str = Field("", description="Azure service endpoint URL")
    role: str = Field(
        "chat", description="Model role: 'chat' for generation, 'embedding' for vectors"
    )

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str, info: ValidationInfo) -> str:
        """Validate that API key is provided when using token authentication."""
        # Check for placeholder values
        if v and "placeholder" in v.lower():
            raise ValueError(
                "API key is required. Set the appropriate environment variable "
                "(e.g., AZURE_OPENAI_API_KEY) or provide a valid key."
            )

        # The authentication_method validation will be handled in model_validator
        # since we need access to all fields. For field validator, we allow
        # empty api_key and let model_validator handle the logic based on auth method.
        return v

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        """Validate that base URL is provided and properly formatted."""
        if v and "placeholder" in v.lower():
            raise ValueError(
                "Base URL is required. Set the appropriate environment variable "
                "(e.g., AZURE_OPENAI_BASE_URL) or provide a valid URL."
            )
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("Base URL must start with 'http://' or 'https://'")
        return v

    @model_validator(mode="after")
    def validate_azure_auth(self) -> "ModelSettings":
        """Validate Azure authentication configuration."""
        # Check if API key is required based on authentication method
        if self.authentication_method == AuthenticationMethod.TOKEN:
            if not self.api_key:
                raise ValueError(
                    "API key is required when authentication_method is "
                    "'token'. Set the appropriate environment variable "
                    "(e.g., AZURE_OPENAI_API_KEY) or provide a valid key."
                )
        elif self.authentication_method == AuthenticationMethod.CLIENT_ID_AND_SECRET:
            if not (self.client_id and self.client_secret and self.tenant_id):
                raise ValueError(
                    "CLIENT_ID_AND_SECRET requires client_id, client_secret, and tenant_id."
                )
        return self


class ChatServiceSettings(BaseModel):
    """Configuration for the chat service backend.

    Defines how the chat service processes conversations.
    Currently supports multi-agent workflows.
    """

    type: str = Field(
        "multi_agent",
        description="Chat service type: 'multi_agent' for agent workflows",
    )


class ToolServiceSettings(BaseModel):
    """Configuration for external tool integrations.

    Enables integration with external tools and services.
    Disable if only using built-in functionality.
    """

    enable: bool = Field(False, description="Enable external tool service integrations")


class LoggingSettings(BaseModel):
    """Configuration for application logging.

    Controls log levels and output formatting.
    Use 'debug' for development, 'info' or 'warning' for production.
    """

    root_log_level: str = Field(
        "info", description="Root logger level: 'debug', 'info', 'warning', 'error'"
    )
    log_level: str = Field(
        "info",
        description="Application logger level: 'debug', 'info', 'warning', 'error'",
    )

    @field_validator("root_log_level", "log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level values."""
        valid_levels = {"debug", "info", "warning", "error", "critical"}
        if v.lower() not in valid_levels:
            raise ValueError(f"Log level must be one of: {', '.join(valid_levels)}")
        return v.lower()


class AzureSearchSettings(BaseModel):
    """Configuration for Azure Cognitive Search integration.

    Enables document search and retrieval capabilities.
    Optional - leave empty if not using Azure Search.
    Contains Azure authentication configuration fields.
    """

    service: str = Field("", description="Azure Search service name")
    endpoint: str = Field("", description="Azure Search service endpoint URL")
    key: str = Field("", description="Azure Search service API key")

    # Azure authentication fields
    authentication_method: AuthenticationMethod = Field(
        default=AuthenticationMethod.TOKEN, description="Authentication method for Azure services"
    )
    api_key: str = Field("", description="API key for token-based authentication")
    client_id: str = Field("", description="Azure client ID for service principal or MSI")
    client_secret: str = Field(
        "", description="Azure client secret for service principal authentication"
    )
    tenant_id: str = Field("", description="Azure tenant ID for service principal authentication")


class AzureSqlSettings(BaseModel):
    """Configuration for Azure SQL integration.

    Enables SQL database operations and queries.
    Optional - leave empty if not using Azure SQL.
    """

    database_name: str = Field("", description="Azure SQL database name")
    table_name: str = Field("", description="Default table name for operations")
    database_connection_string: str = Field("", description="Azure SQL connection string")


class WebAuthenticationSettings(BaseModel):
    """Authentication settings for web interfaces."""

    enable: bool = Field(False, description="Enable web authentication")
    username: str = Field("admin", description="Username for basic authentication")
    password: str = Field("", description="Password for basic authentication")
    type: str = Field("basic", description="Authentication type: 'basic' for HTTP basic auth")
    enable_global_middleware: bool = Field(
        False,
        description="Enable global authentication middleware to protect all endpoints",
    )
    jwt_secret_key: str = Field(
        "",
        description="Secret key for JWT token signing. If empty, uses INGENIOUS_JWT_SECRET_KEY env var",
    )
    jwt_algorithm: str = Field("HS256", description="Algorithm for JWT token signing")
    jwt_access_token_expire_minutes: int = Field(
        1440,
        description="JWT access token expiration time in minutes (default: 24 hours)",
    )
    jwt_refresh_token_expire_days: int = Field(
        7, description="JWT refresh token expiration time in days (default: 7 days)"
    )


class WebSettings(BaseModel):
    """Configuration for web server and API endpoints.

    Controls how the web service is exposed and secured.
    Adjust IP and port based on deployment requirements.
    """

    ip_address: str = Field(
        "0.0.0.0",
        description="IP address to bind the web server (0.0.0.0 for all interfaces)",
    )
    port: int = Field(80, description="Port number for the web server")
    type: str = Field("fastapi", description="Web framework type: 'fastapi' for FastAPI")
    asynchronous: bool = Field(False, description="Enable asynchronous response handling")
    enable_streaming: bool = Field(
        True, description="Enable streaming responses for chat endpoints"
    )
    streaming_chunk_size: int = Field(100, description="Maximum characters per streaming chunk")
    streaming_delay_ms: int = Field(
        50, description="Delay between streaming chunks in milliseconds"
    )
    authentication: WebAuthenticationSettings = Field(
        default_factory=lambda: WebAuthenticationSettings(
            enable=False,
            username="admin",
            password="",
            type="basic",
            enable_global_middleware=False,
            jwt_secret_key="",
            jwt_algorithm="HS256",
            jwt_access_token_expire_minutes=1440,
            jwt_refresh_token_expire_days=7,
        )
    )

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """Validate port number range."""
        if not 1 <= v <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v


class LocalSqlSettings(BaseModel):
    """Configuration for local SQLite database operations.

    Used for local development and testing with sample data.
    Points to CSV files and local database paths.
    """

    database_path: str = Field(
        "/tmp/sample_sql_db", description="Path to local SQLite database file"
    )
    sample_csv_path: str = Field("", description="Path to sample CSV files for data loading")
    sample_database_name: str = Field("sample_sql_db", description="Name for the sample database")


class FileStorageContainerSettings(BaseModel):
    """Configuration for file storage containers.

    Supports both local file system and Azure Blob Storage.
    Contains Azure authentication configuration fields.
    """

    enable: bool = Field(True, description="Enable this storage container")
    storage_type: str = Field(
        "local",
        description="Storage type: 'local' for filesystem, 'azure' for blob storage",
    )
    container_name: str = Field(
        "", description="Container name for Azure storage (ignored for local)"
    )
    path: str = Field("./", description="Storage path (local directory or Azure blob prefix)")
    add_sub_folders: bool = Field(True, description="Create subdirectories for organization")
    url: str = Field("", description="Azure storage account URL (for Azure storage only)")
    token: str = Field("", description="Azure access token (for Azure storage only)")

    # Azure authentication fields
    authentication_method: AuthenticationMethod = Field(
        default=AuthenticationMethod.DEFAULT_CREDENTIAL,
        description="Authentication method for Azure services",
    )
    api_key: str = Field("", description="API key for token-based authentication")
    client_id: str = Field("", description="Azure client ID for service principal or MSI")
    client_secret: str = Field(
        "", description="Azure client secret for service principal authentication"
    )
    tenant_id: str = Field("", description="Azure tenant ID for service principal authentication")
    endpoint: str = Field("", description="Azure service endpoint URL")


class FileStorageSettings(BaseModel):
    """Configuration for file storage system.

    Manages storage for revisions and data files.
    Supports local and cloud storage options.
    """

    revisions: FileStorageContainerSettings = Field(
        default_factory=lambda: FileStorageContainerSettings(
            enable=True,
            storage_type="local",
            container_name="",
            path="./",
            add_sub_folders=True,
            url="",
            token="",
        )
    )
    data: FileStorageContainerSettings = Field(
        default_factory=lambda: FileStorageContainerSettings(
            enable=True,
            storage_type="local",
            container_name="",
            path="./",
            add_sub_folders=True,
            url="",
            token="",
        )
    )


class ReceiverSettings(BaseModel):
    """Configuration for external event receivers.

    Enables integration with external systems that send events.
    Optional - disable if not using external integrations.
    """

    enable: bool = Field(False, description="Enable external event receiver")
    api_url: str = Field("", description="URL for receiving external events")
    api_key: str = Field("DevApiKey", description="API key for authenticating external events")


class CosmosSettings(BaseModel):
    """Configuration for Azure Cosmos DB service.

    Contains Azure authentication configuration fields.
    """

    uri: str = Field(..., description="Azure Cosmos DB account endpoint URL")
    database_name: str = Field(..., description="Azure Cosmos DB database name")

    # Azure authentication fields
    authentication_method: AuthenticationMethod = Field(
        default=AuthenticationMethod.TOKEN, description="Authentication method for Azure services"
    )
    api_key: str = Field("", description="API key for token-based authentication")
    client_id: str = Field("", description="Azure client ID for service principal or MSI")
    client_secret: str = Field(
        "", description="Azure client secret for service principal authentication"
    )
    tenant_id: str = Field("", description="Azure tenant ID for service principal authentication")
    endpoint: str = Field("", description="Azure service endpoint URL")


class CacheSettings(BaseModel):
    """Configuration for response caching.

    Enables caching of API responses, search results, and other computationally
    expensive operations. Supports both in-memory (LRU) and Redis backends.
    """

    enabled: bool = Field(False, description="Enable response caching (disabled by default)")
    backend: str = Field(
        "memory",
        description="Cache backend: 'memory' for in-memory LRU, 'redis' for Redis",
    )
    redis_url: str = Field(
        "redis://localhost:6379",
        description="Redis connection URL (only used if backend='redis')",
    )
    default_ttl: int = Field(
        300,
        description="Default cache TTL in seconds (5 minutes)",
    )
    max_size: int = Field(
        1000,
        description="Maximum number of cached items for in-memory backend",
    )

    @field_validator("backend")
    @classmethod
    def validate_backend(cls, v: str) -> str:
        """Validate cache backend type."""
        valid_backends = {"memory", "redis"}
        if v.lower() not in valid_backends:
            raise ValueError(f"Cache backend must be one of: {', '.join(valid_backends)}")
        return v.lower()

    @field_validator("default_ttl")
    @classmethod
    def validate_default_ttl(cls, v: int) -> int:
        """Validate default TTL value."""
        if v < 0:
            raise ValueError("Default TTL must be non-negative")
        return v

    @field_validator("max_size")
    @classmethod
    def validate_max_size(cls, v: int) -> int:
        """Validate max cache size."""
        if v < 1:
            raise ValueError("Max cache size must be at least 1")
        return v
