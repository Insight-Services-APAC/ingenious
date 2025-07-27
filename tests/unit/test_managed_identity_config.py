"""
Unit tests for managed identity configuration models.
"""

import pytest
from pydantic import ValidationError

from ingenious.config.models import (
    AzureCosmosSettings,
    AzureSearchSettings,
    ModelSettings,
)


class TestModelSettings:
    """Test cases for ModelSettings with managed identity support."""

    def test_model_settings_with_api_key(self):
        """Test ModelSettings with API key authentication."""
        config = ModelSettings(
            model="gpt-4",
            api_key="test_key",
            base_url="https://test.openai.azure.com/",
            use_managed_identity=False
        )
        
        assert config.model == "gpt-4"
        assert config.api_key == "test_key"
        assert config.use_managed_identity is False

    def test_model_settings_with_managed_identity(self):
        """Test ModelSettings with managed identity authentication."""
        config = ModelSettings(
            model="gpt-4",
            base_url="https://test.openai.azure.com/",
            use_managed_identity=True
        )
        
        assert config.model == "gpt-4"
        assert config.api_key == ""
        assert config.use_managed_identity is True

    def test_model_settings_without_auth_fails(self):
        """Test that ModelSettings fails without authentication method."""
        with pytest.raises(ValidationError, match="Either 'api_key' must be provided or 'use_managed_identity' must be True"):
            ModelSettings(
                model="gpt-4",
                base_url="https://test.openai.azure.com/",
                use_managed_identity=False
            )

    def test_model_settings_api_key_with_managed_identity_ok(self):
        """Test that both API key and managed identity can be provided (managed identity takes precedence)."""
        config = ModelSettings(
            model="gpt-4",
            api_key="test_key",
            base_url="https://test.openai.azure.com/",
            use_managed_identity=True
        )
        
        assert config.model == "gpt-4"
        assert config.api_key == "test_key"
        assert config.use_managed_identity is True

    def test_model_settings_placeholder_api_key_fails(self):
        """Test that placeholder API key is rejected."""
        with pytest.raises(ValidationError, match="API key is required"):
            ModelSettings(
                model="gpt-4",
                api_key="placeholder_key",
                base_url="https://test.openai.azure.com/",
                use_managed_identity=False
            )


class TestAzureSearchSettings:
    """Test cases for AzureSearchSettings with managed identity support."""

    def test_azure_search_with_api_key(self):
        """Test AzureSearchSettings with API key authentication."""
        config = AzureSearchSettings(
            service="test-search",
            endpoint="https://test-search.search.windows.net",
            key="test_key",
            use_managed_identity=False
        )
        
        assert config.service == "test-search"
        assert config.key == "test_key"
        assert config.use_managed_identity is False

    def test_azure_search_with_managed_identity(self):
        """Test AzureSearchSettings with managed identity authentication."""
        config = AzureSearchSettings(
            service="test-search",
            endpoint="https://test-search.search.windows.net",
            use_managed_identity=True
        )
        
        assert config.service == "test-search"
        assert config.key == ""
        assert config.use_managed_identity is True

    def test_azure_search_empty_service_ok(self):
        """Test that empty service name is allowed (optional configuration)."""
        config = AzureSearchSettings()
        
        assert config.service == ""
        assert config.key == ""
        assert config.use_managed_identity is False

    def test_azure_search_without_auth_fails(self):
        """Test that AzureSearchSettings fails without authentication when service is configured."""
        with pytest.raises(ValidationError, match="Either 'key' must be provided or 'use_managed_identity' must be True"):
            AzureSearchSettings(
                service="test-search",
                endpoint="https://test-search.search.windows.net",
                use_managed_identity=False
            )


class TestAzureCosmosSettings:
    """Test cases for AzureCosmosSettings with managed identity support."""

    def test_cosmos_with_account_key(self):
        """Test AzureCosmosSettings with account key authentication."""
        config = AzureCosmosSettings(
            endpoint="https://test-cosmos.documents.azure.com:443/",
            key="test_key==",
            database_name="test_db",
            container_name="test_container",
            use_managed_identity=False
        )
        
        assert config.endpoint == "https://test-cosmos.documents.azure.com:443/"
        assert config.key == "test_key=="
        assert config.database_name == "test_db"
        assert config.container_name == "test_container"
        assert config.use_managed_identity is False

    def test_cosmos_with_managed_identity(self):
        """Test AzureCosmosSettings with managed identity authentication."""
        config = AzureCosmosSettings(
            endpoint="https://test-cosmos.documents.azure.com:443/",
            database_name="test_db",
            container_name="test_container",
            use_managed_identity=True
        )
        
        assert config.endpoint == "https://test-cosmos.documents.azure.com:443/"
        assert config.key == ""
        assert config.database_name == "test_db"
        assert config.container_name == "test_container"
        assert config.use_managed_identity is True

    def test_cosmos_empty_endpoint_ok(self):
        """Test that empty endpoint is allowed (optional configuration)."""
        config = AzureCosmosSettings()
        
        assert config.endpoint == ""
        assert config.key == ""
        assert config.use_managed_identity is False

    def test_cosmos_without_auth_fails(self):
        """Test that AzureCosmosSettings fails without authentication when endpoint is configured."""
        with pytest.raises(ValidationError, match="Either 'key' must be provided or 'use_managed_identity' must be True"):
            AzureCosmosSettings(
                endpoint="https://test-cosmos.documents.azure.com:443/",
                database_name="test_db",
                container_name="test_container",
                use_managed_identity=False
            )