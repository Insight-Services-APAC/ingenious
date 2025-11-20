"""Test configuration models."""

import pytest
from ingenious.config.models import (
    LoggingSettings,
    ModelSettings,
    WebSettings,
    ChatHistorySettings,
    WebAuthenticationSettings,
)


class TestLoggingSettings:
    """Test LoggingSettings model."""

    def test_default_initialization(self):
        """Test default logging settings."""
        settings = LoggingSettings()

        assert settings.root_log_level is not None
        assert settings.format is not None

    def test_custom_log_level(self):
        """Test custom log level."""
        settings = LoggingSettings(root_log_level="DEBUG")

        assert settings.root_log_level == "DEBUG"


class TestWebSettings:
    """Test WebSettings model."""

    def test_default_initialization(self):
        """Test default web settings."""
        settings = WebSettings()

        assert settings.port is not None
        assert isinstance(settings.port, int)
        assert settings.host is not None

    def test_custom_port(self):
        """Test custom port."""
        settings = WebSettings(port=3000)

        assert settings.port == 3000


class TestChatHistorySettings:
    """Test ChatHistorySettings model."""

    def test_default_initialization(self):
        """Test default chat history settings."""
        settings = ChatHistorySettings()

        # Check that basic settings exist
        assert hasattr(settings, 'database_client')

    def test_database_client_type(self):
        """Test database client type."""
        settings = ChatHistorySettings(database_client="sqlite")

        assert settings.database_client == "sqlite"


class TestWebAuthenticationSettings:
    """Test WebAuthenticationSettings model."""

    def test_default_initialization(self):
        """Test default authentication settings."""
        settings = WebAuthenticationSettings()

        assert hasattr(settings, 'enable')
        assert isinstance(settings.enable, bool)

    def test_enable_authentication(self):
        """Test enabling authentication."""
        settings = WebAuthenticationSettings(enable=True)

        assert settings.enable is True
