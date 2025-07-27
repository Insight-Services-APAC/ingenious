"""
Unit tests for Cosmos DB service.
"""

from unittest.mock import Mock, patch

import pytest

from ingenious.external_services.cosmos_service import CosmosService


class TestCosmosService:
    """Test cases for Cosmos DB service."""

    def test_init_with_account_key(self):
        """Test CosmosService initialization with account key."""
        endpoint = "https://test-cosmos.documents.azure.com:443/"
        key = "test_key=="
        database_name = "test_db"
        container_name = "test_container"

        with patch("ingenious.external_services.cosmos_service.CosmosClient") as mock_client:
            mock_cosmos_instance = Mock()
            mock_client.return_value = mock_cosmos_instance

            service = CosmosService(
                endpoint=endpoint,
                database_name=database_name,
                container_name=container_name,
                key=key,
                use_managed_identity=False,
            )

            assert service.endpoint == endpoint
            assert service.database_name == database_name
            assert service.container_name == container_name
            assert service.client == mock_cosmos_instance

            mock_client.assert_called_once_with(url=endpoint, credential=key)

    def test_init_with_managed_identity(self):
        """Test CosmosService initialization with managed identity."""
        endpoint = "https://test-cosmos.documents.azure.com:443/"
        database_name = "test_db"
        container_name = "test_container"

        with patch("ingenious.external_services.cosmos_service.CosmosClient") as mock_client, \
             patch("ingenious.external_services.cosmos_service.DefaultAzureCredential") as mock_credential:
            
            mock_cosmos_instance = Mock()
            mock_client.return_value = mock_cosmos_instance
            mock_cred_instance = Mock()
            mock_credential.return_value = mock_cred_instance

            service = CosmosService(
                endpoint=endpoint,
                database_name=database_name,
                container_name=container_name,
                use_managed_identity=True,
            )

            assert service.endpoint == endpoint
            assert service.database_name == database_name
            assert service.container_name == container_name
            assert service.client == mock_cosmos_instance

            mock_credential.assert_called_once()
            mock_client.assert_called_once_with(url=endpoint, credential=mock_cred_instance)

    def test_init_without_key_or_managed_identity_fails(self):
        """Test that initialization fails without key or managed identity."""
        endpoint = "https://test-cosmos.documents.azure.com:443/"
        database_name = "test_db"
        container_name = "test_container"

        with pytest.raises(ValueError, match="Key is required when not using managed identity"):
            CosmosService(
                endpoint=endpoint,
                database_name=database_name,
                container_name=container_name,
                use_managed_identity=False,
            )

    def test_create_document(self):
        """Test document creation."""
        endpoint = "https://test-cosmos.documents.azure.com:443/"
        database_name = "test_db"
        container_name = "test_container"
        key = "test_key=="

        document = {"id": "test_doc", "name": "Test Document"}

        with patch("ingenious.external_services.cosmos_service.CosmosClient") as mock_client:
            mock_cosmos_instance = Mock()
            mock_client.return_value = mock_cosmos_instance
            
            mock_database = Mock()
            mock_container = Mock()
            mock_cosmos_instance.get_database_client.return_value = mock_database
            mock_database.get_container_client.return_value = mock_container
            mock_container.create_item.return_value = {"id": "test_doc", "_ts": 12345}

            service = CosmosService(
                endpoint=endpoint,
                database_name=database_name,
                container_name=container_name,
                key=key,
            )

            result = service.create_document(document)

            assert result == {"id": "test_doc", "_ts": 12345}
            mock_cosmos_instance.get_database_client.assert_called_once_with(database_name)
            mock_database.get_container_client.assert_called_once_with(container_name)
            mock_container.create_item.assert_called_once_with(body=document)

    def test_read_document(self):
        """Test document reading."""
        endpoint = "https://test-cosmos.documents.azure.com:443/"
        database_name = "test_db"
        container_name = "test_container"
        key = "test_key=="

        document_id = "test_doc"
        partition_key = "test_partition"

        with patch("ingenious.external_services.cosmos_service.CosmosClient") as mock_client:
            mock_cosmos_instance = Mock()
            mock_client.return_value = mock_cosmos_instance
            
            mock_database = Mock()
            mock_container = Mock()
            mock_cosmos_instance.get_database_client.return_value = mock_database
            mock_database.get_container_client.return_value = mock_container
            mock_container.read_item.return_value = {"id": "test_doc", "name": "Test Document"}

            service = CosmosService(
                endpoint=endpoint,
                database_name=database_name,
                container_name=container_name,
                key=key,
            )

            result = service.read_document(document_id, partition_key)

            assert result == {"id": "test_doc", "name": "Test Document"}
            mock_cosmos_instance.get_database_client.assert_called_once_with(database_name)
            mock_database.get_container_client.assert_called_once_with(container_name)
            mock_container.read_item.assert_called_once_with(item=document_id, partition_key=partition_key)

    def test_query_documents(self):
        """Test document querying."""
        endpoint = "https://test-cosmos.documents.azure.com:443/"
        database_name = "test_db"
        container_name = "test_container"
        key = "test_key=="

        query = "SELECT * FROM c WHERE c.name = @name"
        parameters = [{"name": "@name", "value": "Test"}]

        with patch("ingenious.external_services.cosmos_service.CosmosClient") as mock_client:
            mock_cosmos_instance = Mock()
            mock_client.return_value = mock_cosmos_instance
            
            mock_database = Mock()
            mock_container = Mock()
            mock_cosmos_instance.get_database_client.return_value = mock_database
            mock_database.get_container_client.return_value = mock_container
            
            # Mock the query results as an iterable
            mock_results = [{"id": "doc1", "name": "Test"}, {"id": "doc2", "name": "Test"}]
            mock_container.query_items.return_value = iter(mock_results)

            service = CosmosService(
                endpoint=endpoint,
                database_name=database_name,
                container_name=container_name,
                key=key,
            )

            result = service.query_documents(query, parameters)

            assert result == mock_results
            mock_cosmos_instance.get_database_client.assert_called_once_with(database_name)
            mock_database.get_container_client.assert_called_once_with(container_name)
            mock_container.query_items.assert_called_once_with(
                query=query, 
                parameters=parameters, 
                max_item_count=None
            )

    def test_update_document(self):
        """Test document updating."""
        endpoint = "https://test-cosmos.documents.azure.com:443/"
        database_name = "test_db"
        container_name = "test_container"
        key = "test_key=="

        document = {"id": "test_doc", "name": "Updated Test Document"}

        with patch("ingenious.external_services.cosmos_service.CosmosClient") as mock_client:
            mock_cosmos_instance = Mock()
            mock_client.return_value = mock_cosmos_instance
            
            mock_database = Mock()
            mock_container = Mock()
            mock_cosmos_instance.get_database_client.return_value = mock_database
            mock_database.get_container_client.return_value = mock_container
            mock_container.replace_item.return_value = {"id": "test_doc", "name": "Updated Test Document", "_ts": 12346}

            service = CosmosService(
                endpoint=endpoint,
                database_name=database_name,
                container_name=container_name,
                key=key,
            )

            result = service.update_document(document)

            assert result == {"id": "test_doc", "name": "Updated Test Document", "_ts": 12346}
            mock_cosmos_instance.get_database_client.assert_called_once_with(database_name)
            mock_database.get_container_client.assert_called_once_with(container_name)
            mock_container.replace_item.assert_called_once_with(item=document, body=document)

    def test_delete_document(self):
        """Test document deletion."""
        endpoint = "https://test-cosmos.documents.azure.com:443/"
        database_name = "test_db"
        container_name = "test_container"
        key = "test_key=="

        document_id = "test_doc"
        partition_key = "test_partition"

        with patch("ingenious.external_services.cosmos_service.CosmosClient") as mock_client:
            mock_cosmos_instance = Mock()
            mock_client.return_value = mock_cosmos_instance
            
            mock_database = Mock()
            mock_container = Mock()
            mock_cosmos_instance.get_database_client.return_value = mock_database
            mock_database.get_container_client.return_value = mock_container

            service = CosmosService(
                endpoint=endpoint,
                database_name=database_name,
                container_name=container_name,
                key=key,
            )

            service.delete_document(document_id, partition_key)

            mock_cosmos_instance.get_database_client.assert_called_once_with(database_name)
            mock_database.get_container_client.assert_called_once_with(container_name)
            mock_container.delete_item.assert_called_once_with(item=document_id, partition_key=partition_key)