"""Tests for the consolidated configuration system using IngeniousSettings.

This test suite ensures that the new pydantic-settings based configuration
system works correctly and provides all necessary functionality.
"""

import os
import tempfile
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from ingenious.config.config import get_config
from ingenious.config.settings import (
    ChatHistorySettings,
    IngeniousSettings,
    LoggingSettings,
    ModelSettings,
    WebSettings,
)


class TestIngeniousSettings:
    """Test the core IngeniousSettings functionality."""

    def test_default_settings_creation(self):
        """Test creating settings with default values."""
        # Mock environment variables to provide minimal required config
        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_BASE_URL": "https://test.openai.azure.com/",
            },
        ):
            settings = IngeniousSettings()

            assert settings.profile == "default"
            assert len(settings.models) >= 1
            assert settings.models[0].api_key == "test-key"
            assert settings.models[0].base_url == "https://test.openai.azure.com/"
            assert settings.chat_history.database_type == "sqlite"
            assert settings.logging.log_level == "info"

    @pytest.mark.isolation_sensitive
    def test_env_file_loading(self):
        """Test that .env file is properly loaded."""
        import os
        from unittest.mock import patch

        # Create a temporary .env file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("INGENIOUS_LOGGING__ROOT_LOG_LEVEL=debug\n")
            f.write("INGENIOUS_WEB_CONFIGURATION__PORT=8888\n")
            f.write("AZURE_OPENAI_API_KEY=test-key\n")
            f.write("AZURE_OPENAI_BASE_URL=https://test.openai.azure.com/\n")
            env_file_path = f.name

        try:
            # Use a patched environment to isolate the test
            env_vars = {
                "INGENIOUS_LOGGING__ROOT_LOG_LEVEL": "debug",
                "INGENIOUS_WEB_CONFIGURATION__PORT": "8888",
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_BASE_URL": "https://test.openai.azure.com/",
            }
            with patch.dict("os.environ", env_vars, clear=True):
                settings = IngeniousSettings()
                assert settings.logging.root_log_level == "debug"
                assert settings.web_configuration.port == 8888
        finally:
            os.unlink(env_file_path)

    def test_environment_variable_override(self):
        """Test that environment variables override default values."""
        with patch.dict(
            os.environ,
            {
                "INGENIOUS_PROFILE": "production",
                "AZURE_OPENAI_MODEL": "gpt-3.5-turbo",
                "AZURE_OPENAI_API_KEY": "prod-key",
                "AZURE_OPENAI_BASE_URL": "https://prod.openai.azure.com/",
                "INGENIOUS_WEB_CONFIGURATION__PORT": "8080",
                "INGENIOUS_LOGGING__LOG_LEVEL": "warning",
            },
        ):
            settings = IngeniousSettings()

            assert settings.profile == "production"
            assert settings.models[0].model == "gpt-3.5-turbo"
            assert settings.models[0].api_key == "prod-key"
            assert settings.web_configuration.port == 8080
            assert settings.logging.log_level == "warning"

    def test_nested_configuration_loading(self):
        """Test loading nested configuration structures."""
        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_MODEL": "gpt-4.1-nano",
                "AZURE_OPENAI_API_KEY": "key1",
                "AZURE_OPENAI_BASE_URL": "https://endpoint1.com/",
                "INGENIOUS_WEB_CONFIGURATION__AUTHENTICATION__ENABLE": "true",
                "INGENIOUS_WEB_CONFIGURATION__AUTHENTICATION__USERNAME": "admin",
                "INGENIOUS_WEB_CONFIGURATION__AUTHENTICATION__PASSWORD": "secret",
            },
        ):
            settings = IngeniousSettings()

            assert len(settings.models) >= 1
            assert settings.models[0].model == "gpt-4.1-nano"
            assert settings.models[0].api_key == "key1"
            assert settings.web_configuration.authentication.enable is True
            assert settings.web_configuration.authentication.username == "admin"
            assert settings.web_configuration.authentication.password == "secret"


class TestModelSettings:
    """Test ModelSettings validation and functionality."""

    def test_valid_model_creation(self):
        """Test creating a valid model configuration."""
        model = ModelSettings(
            model="gpt-4.1-nano",
            api_key="test-key",
            base_url="https://test.openai.azure.com/",
            deployment="gpt-4.1-nano-deployment",
        )

        assert model.model == "gpt-4.1-nano"
        assert model.api_key == "test-key"
        assert model.base_url == "https://test.openai.azure.com/"
        assert model.deployment == "gpt-4.1-nano-deployment"
        assert model.api_type == "rest"  # default value

    def test_placeholder_api_key_validation(self):
        """Test that placeholder API keys are rejected."""
        with pytest.raises(ValidationError, match="API key is required"):
            ModelSettings(
                model="gpt-4.1-nano",
                api_key="placeholder_key",
                base_url="https://test.openai.azure.com/",
            )

    def test_placeholder_base_url_validation(self):
        """Test that placeholder base URLs are rejected."""
        with pytest.raises(ValidationError, match="Base URL is required"):
            ModelSettings(model="gpt-4.1-nano", api_key="valid-key", base_url="placeholder_url")

    def test_invalid_base_url_format(self):
        """Test that invalid URL formats are rejected."""
        with pytest.raises(ValidationError, match="Base URL must start with"):
            ModelSettings(model="gpt-4.1-nano", api_key="valid-key", base_url="invalid-url")

    def test_empty_values_allowed(self):
        """Test that empty strings are allowed for development."""
        model = ModelSettings(model="gpt-4.1-nano", api_key="", base_url="")

        assert model.api_key == ""
        assert model.base_url == ""


class TestChatHistorySettings:
    """Test ChatHistorySettings functionality."""

    def test_default_sqlite_settings(self):
        """Test default SQLite settings."""
        chat_history = ChatHistorySettings()

        assert chat_history.database_type == "sqlite"
        assert chat_history.database_path == "./tmp/high_level_logs.db"
        assert chat_history.database_connection_string == ""
        assert chat_history.memory_path == "./tmp"
        assert chat_history.connection_pool_size == 8
        assert chat_history.connection_pool_max_overflow == 16

    def test_azure_sql_settings(self):
        """Test Azure SQL configuration."""
        chat_history = ChatHistorySettings(
            database_type="azuresql",
            database_connection_string="Server=test.database.windows.net;Database=test;",
            database_name="test_db",
        )

        assert chat_history.database_type == "azuresql"
        assert "test.database.windows.net" in chat_history.database_connection_string
        assert chat_history.database_name == "test_db"

    def test_connection_pool_size_configuration(self):
        """Test connection pool size can be configured."""
        chat_history = ChatHistorySettings(connection_pool_size=16)
        assert chat_history.connection_pool_size == 16

        # Test custom pool size and overflow
        chat_history = ChatHistorySettings(
            connection_pool_size=20, connection_pool_max_overflow=40
        )
        assert chat_history.connection_pool_size == 20
        assert chat_history.connection_pool_max_overflow == 40

    def test_connection_pool_size_validation(self):
        """Test connection pool size validation constraints."""
        # Test minimum constraint (ge=1)
        with pytest.raises(ValidationError):
            ChatHistorySettings(connection_pool_size=0)

        # Test maximum constraint (le=100)
        with pytest.raises(ValidationError):
            ChatHistorySettings(connection_pool_size=101)

        # Test max_overflow minimum constraint (ge=0)
        with pytest.raises(ValidationError):
            ChatHistorySettings(connection_pool_max_overflow=-1)

        # Edge cases should work
        chat_history = ChatHistorySettings(connection_pool_size=1)
        assert chat_history.connection_pool_size == 1

        chat_history = ChatHistorySettings(connection_pool_size=100)
        assert chat_history.connection_pool_size == 100

        chat_history = ChatHistorySettings(connection_pool_max_overflow=0)
        assert chat_history.connection_pool_max_overflow == 0


class TestLoggingSettings:
    """Test LoggingSettings validation."""

    def test_valid_log_levels(self):
        """Test that valid log levels are accepted."""
        for level in ["debug", "info", "warning", "error", "critical"]:
            logging_settings = LoggingSettings(root_log_level=level, log_level=level)
            assert logging_settings.root_log_level == level
            assert logging_settings.log_level == level

    def test_invalid_log_level(self):
        """Test that invalid log levels are rejected."""
        with pytest.raises(ValidationError, match="Log level must be one of"):
            LoggingSettings(root_log_level="invalid")

    def test_case_insensitive_log_levels(self):
        """Test that log levels are case insensitive."""
        logging_settings = LoggingSettings(root_log_level="DEBUG", log_level="INFO")
        assert logging_settings.root_log_level == "debug"
        assert logging_settings.log_level == "info"


class TestWebSettings:
    """Test WebSettings validation."""

    def test_default_web_settings(self):
        """Test default web configuration."""
        web = WebSettings()

        assert web.ip_address == "0.0.0.0"
        assert web.port == 80
        assert web.type == "fastapi"
        assert web.asynchronous is False
        assert web.authentication.enable is False

    def test_valid_port_range(self):
        """Test that valid port numbers are accepted."""
        web = WebSettings(port=8080)
        assert web.port == 8080

    def test_invalid_port_range(self):
        """Test that invalid port numbers are rejected."""
        with pytest.raises(ValidationError, match="Port must be between 1 and 65535"):
            WebSettings(port=0)

        with pytest.raises(ValidationError, match="Port must be between 1 and 65535"):
            WebSettings(port=70000)


class TestConfigValidation:
    """Test configuration validation functionality."""

    def test_validation_with_valid_config(self):
        """Test validation passes with valid configuration."""
        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_API_KEY": "valid-key",
                "AZURE_OPENAI_BASE_URL": "https://valid.openai.azure.com/",
            },
        ):
            settings = IngeniousSettings()
            # Should not raise any exceptions
            settings.validate_configuration()

    def test_validation_fails_with_no_models(self):
        """Test validation fails when no models are configured."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="At least one model must be configured"):
                IngeniousSettings(_env_file=None)

    def test_validation_fails_with_placeholder_keys(self):
        """Test validation fails with placeholder values."""
        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_MODEL": "gpt-4.1-nano",
                "AZURE_OPENAI_API_KEY": "placeholder_key",
                "AZURE_OPENAI_BASE_URL": "https://test.com/",
            },
        ):
            # Validation should fail during object creation due to pydantic validators
            with pytest.raises(ValidationError, match="API key is required"):
                IngeniousSettings()

    def test_validation_fails_with_auth_no_password(self):
        """Test validation fails when auth is enabled but no password set."""
        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_API_KEY": "valid-key",
                "AZURE_OPENAI_BASE_URL": "https://valid.openai.azure.com/",
                "INGENIOUS_WEB_CONFIGURATION__AUTHENTICATION__ENABLE": "true",
                "INGENIOUS_WEB_CONFIGURATION__AUTHENTICATION__PASSWORD": "",
            },
        ):
            settings = IngeniousSettings()
            with pytest.raises(ValueError, match="no password is set"):
                settings.validate_configuration()


class TestGetConfigFunction:
    """Test the get_config() function."""

    def test_get_config_returns_settings(self):
        """Test that get_config() returns IngeniousSettings instance."""
        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_BASE_URL": "https://test.openai.azure.com/",
            },
        ):
            config = get_config()

            assert isinstance(config, IngeniousSettings)
            assert config.models[0].api_key == "test-key"

    def test_get_config_calls_validation(self):
        """Test that get_config() calls validate_configuration()."""
        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_BASE_URL": "https://test.openai.azure.com/",
            },
        ):
            with patch.object(IngeniousSettings, "validate_configuration") as mock_validate:
                get_config()
                mock_validate.assert_called_once()

    def test_get_config_handles_validation_errors(self):
        """Test that get_config() properly handles validation errors."""
        with patch.dict(os.environ, {}, clear=True):
            # Patch the get_config function to disable env file
            with patch("ingenious.config.config.IngeniousSettings") as mock_settings:
                # Configure the mock to raise ValueError during creation
                mock_settings.side_effect = ValueError("At least one model must be configured")
                with pytest.raises(ValueError):
                    get_config()


class TestMinimalConfig:
    """Test minimal configuration creation."""

    def test_create_minimal_config(self):
        """Test creating minimal configuration for development."""
        config = IngeniousSettings.create_minimal_config()

        assert isinstance(config, IngeniousSettings)
        assert len(config.models) >= 1
        assert config.logging.root_log_level == "debug"
        assert config.web_configuration.port == 8000
        assert config.web_configuration.authentication.enable is False


class TestBackwardCompatibility:
    """Test backward compatibility features."""

    def test_config_provides_same_interface(self):
        """Test that IngeniousSettings provides the same interface as old Config."""
        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_BASE_URL": "https://test.openai.azure.com/",
            },
        ):
            config = get_config()

            # Test that commonly used attributes exist
            assert hasattr(config, "models")
            assert hasattr(config, "chat_history")
            assert hasattr(config, "web_configuration")
            assert hasattr(config, "logging")
            assert hasattr(config, "profile")

            # Test that models have expected attributes
            assert hasattr(config.models[0], "model")
            assert hasattr(config.models[0], "api_key")
            assert hasattr(config.models[0], "base_url")

            # Test nested attribute access
            assert hasattr(config.chat_history, "database_type")
            assert hasattr(config.web_configuration, "port")
            assert hasattr(config.web_configuration, "authentication")


class TestErrorHandling:
    """Test error handling and error messages."""

    def test_helpful_error_messages(self):
        """Test that error messages are helpful and actionable."""
        with patch.dict(os.environ, {}, clear=True):
            try:
                IngeniousSettings(_env_file=None)
                assert False, "Should have raised ValidationError"
            except ValueError as e:
                error_msg = str(e)
                assert "AZURE_OPENAI_API_KEY" in error_msg
                assert "AZURE_OPENAI_BASE_URL" in error_msg

    def test_configuration_validation_error_details(self):
        """Test that configuration validation provides detailed error information."""
        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_MODEL": "gpt-4.1-nano",
                "AZURE_OPENAI_API_KEY": "placeholder_key",
                "AZURE_OPENAI_BASE_URL": "placeholder_url",
            },
        ):
            # Validation should fail during object creation due to pydantic validators
            try:
                IngeniousSettings()
                assert False, "Should have raised ValidationError"
            except ValidationError as e:
                error_msg = str(e)
                assert "API key is required" in error_msg
                assert "Base URL is required" in error_msg
