"""
Azure Cosmos DB service for document operations.

Provides a unified interface for Cosmos DB operations with support for
both key-based and managed identity authentication.
"""

from typing import Any, Dict, List, Optional

from azure.cosmos import CosmosClient, exceptions
from azure.identity import DefaultAzureCredential

from ingenious.core.structured_logging import get_logger

logger = get_logger(__name__)


class CosmosService:
    """Service for Azure Cosmos DB operations with managed identity support."""

    def __init__(
        self,
        endpoint: str,
        database_name: str,
        container_name: str,
        key: Optional[str] = None,
        use_managed_identity: bool = False,
    ):
        """Initialize Cosmos service.
        
        Args:
            endpoint: Cosmos DB account endpoint URL
            database_name: Default database name
            container_name: Default container name
            key: Account key (optional if using managed identity)
            use_managed_identity: Use managed identity instead of key
        """
        self.endpoint = endpoint
        self.database_name = database_name
        self.container_name = container_name
        
        if use_managed_identity:
            # Use managed identity authentication
            credential = DefaultAzureCredential()
            self.client = CosmosClient(url=endpoint, credential=credential)
            logger.info("Initialized Cosmos client with managed identity", endpoint=endpoint)
        else:
            # Use key authentication
            if not key:
                raise ValueError("Key is required when not using managed identity")
            self.client = CosmosClient(url=endpoint, credential=key)
            logger.info("Initialized Cosmos client with key authentication", endpoint=endpoint)

    def create_document(
        self, 
        document: Dict[str, Any], 
        database_name: Optional[str] = None,
        container_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a document in the specified container.
        
        Args:
            document: Document to create
            database_name: Database name (uses default if not provided)
            container_name: Container name (uses default if not provided)
            
        Returns:
            Created document with metadata
        """
        db_name = database_name or self.database_name
        cont_name = container_name or self.container_name
        
        try:
            database = self.client.get_database_client(db_name)
            container = database.get_container_client(cont_name)
            
            result = container.create_item(body=document)
            logger.debug(
                "Document created successfully",
                database=db_name,
                container=cont_name,
                document_id=result.get("id")
            )
            return result
        except exceptions.CosmosHttpResponseError as e:
            logger.error(
                "Failed to create document",
                database=db_name,
                container=cont_name,
                error=str(e),
                status_code=e.status_code
            )
            raise

    def read_document(
        self, 
        document_id: str, 
        partition_key: Any,
        database_name: Optional[str] = None,
        container_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Read a document by ID and partition key.
        
        Args:
            document_id: Document ID
            partition_key: Partition key value
            database_name: Database name (uses default if not provided)
            container_name: Container name (uses default if not provided)
            
        Returns:
            Document data
        """
        db_name = database_name or self.database_name
        cont_name = container_name or self.container_name
        
        try:
            database = self.client.get_database_client(db_name)
            container = database.get_container_client(cont_name)
            
            result = container.read_item(item=document_id, partition_key=partition_key)
            logger.debug(
                "Document read successfully",
                database=db_name,
                container=cont_name,
                document_id=document_id
            )
            return result
        except exceptions.CosmosResourceNotFoundError:
            logger.warning(
                "Document not found",
                database=db_name,
                container=cont_name,
                document_id=document_id
            )
            raise
        except exceptions.CosmosHttpResponseError as e:
            logger.error(
                "Failed to read document",
                database=db_name,
                container=cont_name,
                document_id=document_id,
                error=str(e),
                status_code=e.status_code
            )
            raise

    def query_documents(
        self, 
        query: str, 
        parameters: Optional[List[Dict[str, Any]]] = None,
        database_name: Optional[str] = None,
        container_name: Optional[str] = None,
        max_item_count: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Query documents using SQL syntax.
        
        Args:
            query: SQL query string
            parameters: Query parameters
            database_name: Database name (uses default if not provided)
            container_name: Container name (uses default if not provided)
            max_item_count: Maximum number of items to return
            
        Returns:
            List of matching documents
        """
        db_name = database_name or self.database_name
        cont_name = container_name or self.container_name
        
        try:
            database = self.client.get_database_client(db_name)
            container = database.get_container_client(cont_name)
            
            results = list(container.query_items(
                query=query,
                parameters=parameters or [],
                max_item_count=max_item_count
            ))
            
            logger.debug(
                "Documents queried successfully",
                database=db_name,
                container=cont_name,
                result_count=len(results)
            )
            return results
        except exceptions.CosmosHttpResponseError as e:
            logger.error(
                "Failed to query documents",
                database=db_name,
                container=cont_name,
                query=query,
                error=str(e),
                status_code=e.status_code
            )
            raise

    def update_document(
        self, 
        document: Dict[str, Any],
        database_name: Optional[str] = None,
        container_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update an existing document.
        
        Args:
            document: Document with updates (must include id and partition key)
            database_name: Database name (uses default if not provided)
            container_name: Container name (uses default if not provided)
            
        Returns:
            Updated document with metadata
        """
        db_name = database_name or self.database_name
        cont_name = container_name or self.container_name
        
        try:
            database = self.client.get_database_client(db_name)
            container = database.get_container_client(cont_name)
            
            result = container.replace_item(item=document, body=document)
            logger.debug(
                "Document updated successfully",
                database=db_name,
                container=cont_name,
                document_id=result.get("id")
            )
            return result
        except exceptions.CosmosHttpResponseError as e:
            logger.error(
                "Failed to update document",
                database=db_name,
                container=cont_name,
                document_id=document.get("id"),
                error=str(e),
                status_code=e.status_code
            )
            raise

    def delete_document(
        self, 
        document_id: str, 
        partition_key: Any,
        database_name: Optional[str] = None,
        container_name: Optional[str] = None
    ) -> None:
        """Delete a document by ID and partition key.
        
        Args:
            document_id: Document ID
            partition_key: Partition key value
            database_name: Database name (uses default if not provided)
            container_name: Container name (uses default if not provided)
        """
        db_name = database_name or self.database_name
        cont_name = container_name or self.container_name
        
        try:
            database = self.client.get_database_client(db_name)
            container = database.get_container_client(cont_name)
            
            container.delete_item(item=document_id, partition_key=partition_key)
            logger.debug(
                "Document deleted successfully",
                database=db_name,
                container=cont_name,
                document_id=document_id
            )
        except exceptions.CosmosResourceNotFoundError:
            logger.warning(
                "Document not found for deletion",
                database=db_name,
                container=cont_name,
                document_id=document_id
            )
            raise
        except exceptions.CosmosHttpResponseError as e:
            logger.error(
                "Failed to delete document",
                database=db_name,
                container=cont_name,
                document_id=document_id,
                error=str(e),
                status_code=e.status_code
            )
            raise