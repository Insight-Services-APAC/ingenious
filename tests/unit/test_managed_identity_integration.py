"""
Integration tests for managed identity configuration.
"""

import pytest

from ingenious.config.main_settings import IngeniousSettings


class TestManagedIdentityIntegration:
    """Integration tests for managed identity support."""

    def test_openai_with_managed_identity_config(self):
        """Test that OpenAI model configuration works with managed identity."""
        settings = IngeniousSettings(
            models=[{
                "model": "gpt-4",
                "base_url": "https://test.openai.azure.com/",
                "use_managed_identity": True,
                "api_version": "2024-02-01"
            }]
        )
        
        assert len(settings.models) == 1
        model = settings.models[0]
        assert model.model == "gpt-4"
        assert model.use_managed_identity is True
        assert model.api_key == ""
        assert model.base_url == "https://test.openai.azure.com/"

    def test_azure_search_with_managed_identity_config(self):
        """Test that Azure Search configuration works with managed identity."""
        settings = IngeniousSettings(
            models=[{
                "model": "gpt-4",
                "api_key": "test",
                "base_url": "https://test.openai.azure.com/"
            }],
            azure_search_services=[{
                "service": "test-search",
                "endpoint": "https://test-search.search.windows.net",
                "use_managed_identity": True
            }]
        )
        
        assert len(settings.azure_search_services) == 1
        search = settings.azure_search_services[0]
        assert search.service == "test-search"
        assert search.use_managed_identity is True
        assert search.key == ""

    def test_azure_cosmos_with_managed_identity_config(self):
        """Test that Azure Cosmos configuration works with managed identity."""
        settings = IngeniousSettings(
            models=[{
                "model": "gpt-4",
                "api_key": "test",
                "base_url": "https://test.openai.azure.com/"
            }],
            azure_cosmos_services={
                "endpoint": "https://test-cosmos.documents.azure.com:443/",
                "database_name": "test_db",
                "container_name": "test_container",
                "use_managed_identity": True
            }
        )
        
        cosmos = settings.azure_cosmos_services
        assert cosmos is not None
        assert cosmos.endpoint == "https://test-cosmos.documents.azure.com:443/"
        assert cosmos.use_managed_identity is True
        assert cosmos.key == ""
        assert cosmos.database_name == "test_db"
        assert cosmos.container_name == "test_container"

    def test_mixed_authentication_methods(self):
        """Test that different services can use different authentication methods."""
        settings = IngeniousSettings(
            models=[{
                "model": "gpt-4",
                "api_key": "test_key",
                "base_url": "https://test.openai.azure.com/",
                "use_managed_identity": False
            }],
            azure_search_services=[{
                "service": "test-search",
                "endpoint": "https://test-search.search.windows.net",
                "use_managed_identity": True
            }],
            azure_cosmos_services={
                "endpoint": "https://test-cosmos.documents.azure.com:443/",
                "key": "test_key==",
                "database_name": "test_db",
                "container_name": "test_container",
                "use_managed_identity": False
            }
        )
        
        # OpenAI uses API key
        model = settings.models[0]
        assert model.use_managed_identity is False
        assert model.api_key == "test_key"
        
        # Search uses managed identity
        search = settings.azure_search_services[0]
        assert search.use_managed_identity is True
        assert search.key == ""
        
        # Cosmos uses account key
        cosmos = settings.azure_cosmos_services
        assert cosmos.use_managed_identity is False
        assert cosmos.key == "test_key=="

    def test_environment_variable_parsing(self):
        """Test that managed identity settings can be parsed from environment variables."""
        # This simulates how environment variables would be parsed
        env_data = {
            "models": {
                "0": {
                    "model": "gpt-4",
                    "base_url": "https://test.openai.azure.com/",
                    "use_managed_identity": True,
                    "api_version": "2024-02-01"
                }
            },
            "azure_search_services": {
                "0": {
                    "service": "test-search",
                    "endpoint": "https://test-search.search.windows.net",
                    "use_managed_identity": True
                }
            },
            "azure_cosmos_services": {
                "endpoint": "https://test-cosmos.documents.azure.com:443/",
                "database_name": "test_db",
                "container_name": "test_container",
                "use_managed_identity": True
            }
        }
        
        settings = IngeniousSettings(**env_data)
        
        # Verify all configurations
        assert settings.models[0].use_managed_identity is True
        assert settings.azure_search_services[0].use_managed_identity is True
        assert settings.azure_cosmos_services.use_managed_identity is True