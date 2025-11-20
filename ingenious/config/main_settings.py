"""Main settings class for Ingenious application.

This module contains the primary IngeniousSettings class that combines
all configuration models and provides the main configuration interface.
"""

import json
from typing import Any, List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

from .environment import get_settings_config
from .models import (
    AzureSearchSettings,
    AzureSqlSettings,
    CacheSettings,
    ChatHistorySettings,
    ChatServiceSettings,
    CosmosSettings,
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

    models: List[ModelSettings] = Field(default_factory=list, description="AI model configurations")

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

    cosmos_service: Optional[CosmosSettings] = Field(
        default=None, description="Azure Cosmos DB service configuration (optional)"
    )

    cache: CacheSettings = Field(
        default_factory=lambda: CacheSettings(),
        description="Response caching configuration",
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
    def validate_models_not_empty_field(cls, v: List[ModelSettings]) -> List[ModelSettings]:
        """Ensure at least one model is configured and handle legacy environment variables."""
        import os

        # Handle legacy environment variables before validation
        legacy_api_key = os.getenv("AZURE_OPENAI_API_KEY")
        legacy_base_url = os.getenv("AZURE_OPENAI_BASE_URL")
        legacy_model = os.getenv("AZURE_OPENAI_MODEL")
        legacy_version = os.getenv("AZURE_OPENAI_VERSION", "2024-06-01")

        # If legacy variables exist and models were created, update them
        if legacy_api_key and legacy_base_url and v:
            # Update the first model with legacy values
            if len(v) > 0:
                model = v[0]
                # Update the model with legacy values
                v[0] = ModelSettings(
                    model=legacy_model or model.model,
                    api_key=legacy_api_key,
                    base_url=legacy_base_url,
                    api_version=legacy_version,
                    api_type=model.api_type,
                    deployment=legacy_model or model.deployment,
                    database_type="test" if os.getenv("PYTEST_CURRENT_TEST") else "default",
                )

        return validate_models_not_empty(v)

    def model_post_init(self, __context: Any) -> None:
        """Initialize default model if none provided but env vars are available."""
        import os

        # Get legacy Azure OpenAI environment variables
        legacy_api_key = os.getenv("AZURE_OPENAI_API_KEY")
        legacy_base_url = os.getenv("AZURE_OPENAI_BASE_URL")
        legacy_model = os.getenv("AZURE_OPENAI_MODEL", "gpt-4.1-nano")

        # If legacy Azure OpenAI env vars are present, set up basic defaults
        if legacy_api_key and legacy_base_url:
            # If no models are configured, create a default model
            if not self.models:
                from .models import ModelSettings

                default_model = ModelSettings(
                    model=legacy_model,
                    api_type="rest",
                    api_version="2023-03-15-preview",
                    api_key=legacy_api_key,
                    base_url=legacy_base_url,
                    deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", legacy_model),
                )
                self.models = [default_model]
            else:
                # If models exist, apply legacy env vars as overrides
                for model in self.models:
                    if legacy_api_key:
                        model.api_key = legacy_api_key
                    if legacy_base_url:
                        model.base_url = legacy_base_url
                    # Also update the model name if specified
                    if os.getenv("AZURE_OPENAI_MODEL"):
                        model.model = legacy_model

            # Set basic defaults for testing scenarios
            if self.chat_history.database_type == "cosmos":
                # When using legacy env vars, default to sqlite for simplicity
                self.chat_history.database_type = "sqlite"

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
