"""
Main settings class for Ingenious application.

This module contains the primary IngeniousSettings class that combines
all configuration models and provides the main configuration interface.
"""

import json
from typing import Any, List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

from .environment import get_settings_config
from .models import (
    AzureCosmosSettings,
    AzureSearchSettings,
    AzureSqlSettings,
    ChatHistorySettings,
    ChatServiceSettings,
    FileStorageSettings,
    LocalSqlSettings,
    LoggingSettings,
    ModelSettings,
    ReceiverSettings,
    ToolServiceSettings,
    WebSettings,
)
from .validators import validate_configuration, validate_models_not_empty


class IngeniousSettings(BaseSettings):
    """Main settings class for Ingenious application.

    This class automatically loads configuration from:
    1. Environment variables (with INGENIOUS_ prefix)
    2. .env files (.env, .env.local, .env.dev, .env.prod)
    3. Default values defined in the model

    Example usage:
        settings = IngeniousSettings()
        print(f"Web server will run on port {settings.web_configuration.port}")

    Environment variable examples:
        INGENIOUS_WEB_CONFIGURATION__PORT=8080
        INGENIOUS_MODELS__0__API_KEY=your-api-key
        INGENIOUS_LOGGING__ROOT_LOG_LEVEL=debug
    """

    model_config = get_settings_config()

    profile: str = Field(
        "default", description="Profile name to use for environment-specific settings"
    )

    chat_history: ChatHistorySettings = Field(
        default_factory=lambda: ChatHistorySettings(),
        description="Chat history storage configuration",
    )

    models: List[ModelSettings] = Field(
        default_factory=list, description="AI model configurations"
    )

    logging: LoggingSettings = Field(
        default_factory=lambda: LoggingSettings(),
        description="Application logging configuration",
    )

    tool_service: ToolServiceSettings = Field(
        default_factory=lambda: ToolServiceSettings(),
        description="External tool service configuration",
    )

    chat_service: ChatServiceSettings = Field(
        default_factory=lambda: ChatServiceSettings(),
        description="Chat service backend configuration",
    )

    web_configuration: WebSettings = Field(
        default_factory=lambda: WebSettings(),
        description="Web server and API configuration",
    )

    receiver_configuration: ReceiverSettings = Field(
        default_factory=lambda: ReceiverSettings(),
        description="External event receiver configuration",
    )

    local_sql_db: LocalSqlSettings = Field(
        default_factory=lambda: LocalSqlSettings(),
        description="Local SQLite database configuration",
    )

    file_storage: FileStorageSettings = Field(
        default_factory=lambda: FileStorageSettings(),
        description="File storage system configuration",
    )

    azure_search_services: Optional[List[AzureSearchSettings]] = Field(
        default=None,
        description="Azure Cognitive Search service configurations (optional)",
    )

    azure_sql_services: Optional[AzureSqlSettings] = Field(
        default=None, description="Azure SQL service configuration (optional)"
    )

    azure_cosmos_services: Optional[AzureCosmosSettings] = Field(
        default=None, description="Azure Cosmos DB service configuration (optional)"
    )

    @field_validator("models", mode="before")
    @classmethod
    def parse_models_field(cls, v: Any) -> Any:
        """Parse models from JSON string or nested environment variables."""
        # Handle JSON string format (e.g., INGENIOUS_MODELS='[{...}]')
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # If not valid JSON, let pydantic handle the error
                return v

        # Handle dictionary format from nested env vars (e.g., INGENIOUS_MODELS__0__*)
        if isinstance(v, dict):
            # Convert {'0': {...}, '1': {...}} to [{...}, {...}]
            result = []
            for key in sorted(v.keys()):
                if key.isdigit():
                    result.append(v[key])
            return result

        return v

    @field_validator("azure_search_services", mode="before")
    @classmethod
    def parse_azure_search_services_field(cls, v: Any) -> Any:
        """Parse azure_search_services from JSON string or nested environment variables."""
        # Handle JSON string format (e.g., INGENIOUS_AZURE_SEARCH_SERVICES='[{...}]')
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # If not valid JSON, let pydantic handle the error
                return v

        # Handle dictionary format from nested env vars (e.g., INGENIOUS_AZURE_SEARCH_SERVICES__0__*)
        if isinstance(v, dict):
            # Convert {'0': {...}, '1': {...}} to [{...}, {...}]
            result = []
            for key in sorted(v.keys()):
                if key.isdigit():
                    result.append(v[key])
            return result

        return v

    @field_validator("models")
    @classmethod
    def validate_models_not_empty_field(
        cls, v: List[ModelSettings]
    ) -> List[ModelSettings]:
        """Ensure at least one model is configured."""
        return validate_models_not_empty(v)

    def validate_configuration(self) -> None:
        """Validate the complete configuration and provide helpful feedback."""
        validate_configuration(self)

    @classmethod
    def load_from_env_file(cls, env_file: str = ".env") -> "IngeniousSettings":
        """Load settings from a specific .env file."""
        return cls(_env_file=env_file)

    @classmethod
    def create_minimal_config(cls) -> "IngeniousSettings":
        """Create a minimal configuration for development."""
        from .environment import create_minimal_config

        return create_minimal_config()
