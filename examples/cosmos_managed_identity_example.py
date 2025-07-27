"""
Example usage of the Cosmos DB service with managed identity.

This example demonstrates how to use the new CosmosService
to perform basic document operations with both key-based
and managed identity authentication.
"""

from ingenious.external_services.cosmos_service import CosmosService


def example_with_account_key():
    """Example using account key authentication."""
    
    # Initialize service with account key
    cosmos = CosmosService(
        endpoint="https://your-cosmos-account.documents.azure.com:443/",
        database_name="example_db",
        container_name="example_container",
        key="your-account-key-here==",
        use_managed_identity=False
    )
    
    # Create a document
    document = {
        "id": "user-123",
        "name": "John Doe",
        "email": "john.doe@example.com",
        "category": "user"
    }
    
    result = cosmos.create_document(document)
    print(f"Created document: {result['id']}")
    
    # Read the document
    retrieved_doc = cosmos.read_document("user-123", "user")
    print(f"Retrieved: {retrieved_doc['name']}")
    
    # Query documents
    query = "SELECT * FROM c WHERE c.category = @category"
    parameters = [{"name": "@category", "value": "user"}]
    results = cosmos.query_documents(query, parameters)
    print(f"Query returned {len(results)} documents")
    
    # Update the document
    document["email"] = "john.updated@example.com"
    updated_doc = cosmos.update_document(document)
    print(f"Updated document: {updated_doc['id']}")
    
    # Delete the document
    cosmos.delete_document("user-123", "user")
    print("Document deleted")


def example_with_managed_identity():
    """Example using managed identity authentication."""
    
    # Initialize service with managed identity
    cosmos = CosmosService(
        endpoint="https://your-cosmos-account.documents.azure.com:443/",
        database_name="example_db",
        container_name="example_container",
        use_managed_identity=True  # No key required!
    )
    
    # Same operations as above work identically
    document = {
        "id": "user-456",
        "name": "Jane Smith",
        "email": "jane.smith@example.com",
        "category": "user"
    }
    
    result = cosmos.create_document(document)
    print(f"Created document with managed identity: {result['id']}")


def example_from_configuration():
    """Example using configuration from settings."""
    from ingenious.config.main_settings import IngeniousSettings
    
    # Load configuration
    settings = IngeniousSettings()
    
    if settings.azure_cosmos_services:
        cosmos_config = settings.azure_cosmos_services
        
        # Initialize service based on configuration
        cosmos = CosmosService(
            endpoint=cosmos_config.endpoint,
            database_name=cosmos_config.database_name,
            container_name=cosmos_config.container_name,
            key=cosmos_config.key if not cosmos_config.use_managed_identity else None,
            use_managed_identity=cosmos_config.use_managed_identity
        )
        
        # Use the service
        documents = cosmos.query_documents("SELECT * FROM c")
        print(f"Found {len(documents)} documents in database")
    else:
        print("Cosmos DB not configured")


if __name__ == "__main__":
    print("Example 1: Using account key")
    try:
        example_with_account_key()
    except Exception as e:
        print(f"Account key example failed (expected in demo): {e}")
    
    print("\nExample 2: Using managed identity")
    try:
        example_with_managed_identity()
    except Exception as e:
        print(f"Managed identity example failed (expected in demo): {e}")
    
    print("\nExample 3: Using configuration")
    try:
        example_from_configuration()
    except Exception as e:
        print(f"Configuration example: {e}")