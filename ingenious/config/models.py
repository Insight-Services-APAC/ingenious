"""
Pydantic models for configuration settings.

This module contains all the BaseModel classes that define
the structure and validation for different configuration sections.
"""

from pydantic import BaseModel, Field, field_validator


class ChatHistorySettings(BaseModel):
    """Configuration for chat history storage.

    Supports both SQLite (local) and Azure SQL (cloud) storage options.
    For local development, SQLite is recommended. For production, use Azure SQL.
    """

    database_type: str = Field(
        "sqlite",
        description="Type of database: 'sqlite' for local, 'azuresql' for cloud",
    )
    database_path: str = Field(
        "./tmp/high_level_logs.db",
        description="File path for SQLite database (ignored for Azure SQL)",
    )
    database_connection_string: str = Field(
        "", description="Connection string for Azure SQL (leave empty for SQLite)"
    )
    database_name: str = Field(
        "", description="Database name for Azure SQL (ignored for SQLite)"
    )
    memory_path: str = Field(
        "./tmp", description="Path for memory storage and temporary files"
    )


class ModelSettings(BaseModel):
    """Configuration for AI models.

    Defines which AI models to use and how to connect to them.
    Supports Azure OpenAI, OpenAI, and other compatible endpoints.
    Supports both API key and managed identity authentication.
    """

    model: str = Field(..., description="Model name (e.g., 'gpt-4', 'gpt-3.5-turbo')")
    api_type: str = Field("rest", description="API type: 'rest' for HTTP APIs")
    api_version: str = Field(
        "2023-03-15-preview", description="API version for Azure OpenAI"
    )
    deployment: str = Field("", description="Azure OpenAI deployment name (optional)")
    api_key: str = Field("", description="API key for the model service (optional if using managed identity)")
    base_url: str = Field("", description="Base URL for the API endpoint")
    use_managed_identity: bool = Field(
        False, description="Use Azure managed identity for authentication instead of API key"
    )

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str, info) -> str:
        """Validate that API key is provided when not using managed identity."""
        if v and "placeholder" in v.lower():
            raise ValueError(
                "API key is required. Set the appropriate environment variable "
                "(e.g., AZURE_OPENAI_API_KEY) or provide a valid key."
            )
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

    def model_post_init(self, __context) -> None:
        """Validate that either API key or managed identity is configured."""
        if not self.use_managed_identity and not self.api_key:
            raise ValueError(
                "Either 'api_key' must be provided or 'use_managed_identity' must be True"
            )


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
    Supports both API key and managed identity authentication.
    Optional - leave empty if not using Azure Search.
    """

    service: str = Field("", description="Azure Search service name")
    endpoint: str = Field("", description="Azure Search service endpoint URL")
    key: str = Field("", description="Azure Search service API key (optional if using managed identity)")
    use_managed_identity: bool = Field(
        False, description="Use Azure managed identity for authentication instead of API key"
    )

    def model_post_init(self, __context) -> None:
        """Validate that either API key or managed identity is configured when service is provided."""
        if self.service and not self.use_managed_identity and not self.key:
            raise ValueError(
                "Either 'key' must be provided or 'use_managed_identity' must be True when service is configured"
            )


class AzureSqlSettings(BaseModel):
    """Configuration for Azure SQL integration.

    Enables SQL database operations and queries.
    Optional - leave empty if not using Azure SQL.
    """

    database_name: str = Field("", description="Azure SQL database name")
    table_name: str = Field("", description="Default table name for operations")
    database_connection_string: str = Field(
        "", description="Azure SQL connection string"
    )


class AzureCosmosSettings(BaseModel):
    """Configuration for Azure Cosmos DB integration.

    Enables NoSQL document database operations.
    Supports both connection string and managed identity authentication.
    Optional - leave empty if not using Azure Cosmos DB.
    """

    endpoint: str = Field("", description="Azure Cosmos DB account endpoint URL")
    key: str = Field("", description="Azure Cosmos DB account key (optional if using managed identity)")
    database_name: str = Field("", description="Default database name for operations")
    container_name: str = Field("", description="Default container name for operations")
    use_managed_identity: bool = Field(
        False, description="Use Azure managed identity for authentication instead of account key"
    )

    def model_post_init(self, __context) -> None:
        """Validate that either account key or managed identity is configured when endpoint is provided."""
        if self.endpoint and not self.use_managed_identity and not self.key:
            raise ValueError(
                "Either 'key' must be provided or 'use_managed_identity' must be True when endpoint is configured"
            )


class WebAuthenticationSettings(BaseModel):
    """Authentication settings for web interfaces."""

    enable: bool = Field(False, description="Enable web authentication")
    username: str = Field("admin", description="Username for basic authentication")
    password: str = Field("", description="Password for basic authentication")
    type: str = Field(
        "basic", description="Authentication type: 'basic' for HTTP basic auth"
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
    type: str = Field(
        "fastapi", description="Web framework type: 'fastapi' for FastAPI"
    )
    asynchronous: bool = Field(
        False, description="Enable asynchronous response handling"
    )
    authentication: WebAuthenticationSettings = WebAuthenticationSettings()

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
    sample_csv_path: str = Field(
        "", description="Path to sample CSV files for data loading"
    )
    sample_database_name: str = Field(
        "sample_sql_db", description="Name for the sample database"
    )


class FileStorageContainerSettings(BaseModel):
    """Configuration for file storage containers.

    Supports both local file system and Azure Blob Storage.
    """

    enable: bool = Field(True, description="Enable this storage container")
    storage_type: str = Field(
        "local",
        description="Storage type: 'local' for filesystem, 'azure' for blob storage",
    )
    container_name: str = Field(
        "", description="Container name for Azure storage (ignored for local)"
    )
    path: str = Field(
        "./", description="Storage path (local directory or Azure blob prefix)"
    )
    add_sub_folders: bool = Field(
        True, description="Create subdirectories for organization"
    )
    url: str = Field(
        "", description="Azure storage account URL (for Azure storage only)"
    )
    client_id: str = Field(
        "", description="Azure client ID for authentication (for Azure storage only)"
    )
    token: str = Field("", description="Azure access token (for Azure storage only)")
    authentication_method: str = Field(
        "default_credential",
        description="Authentication method for Azure: 'default_credential', 'msi', etc.",
    )


class FileStorageSettings(BaseModel):
    """Configuration for file storage system.

    Manages storage for revisions and data files.
    Supports local and cloud storage options.
    """

    revisions: FileStorageContainerSettings = FileStorageContainerSettings()
    data: FileStorageContainerSettings = FileStorageContainerSettings()


class ReceiverSettings(BaseModel):
    """Configuration for external event receivers.

    Enables integration with external systems that send events.
    Optional - disable if not using external integrations.
    """

    enable: bool = Field(False, description="Enable external event receiver")
    api_url: str = Field("", description="URL for receiving external events")
    api_key: str = Field(
        "DevApiKey", description="API key for authenticating external events"
    )
