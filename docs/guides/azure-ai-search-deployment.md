# Azure AI Search Deployment Guide

This guide provides step-by-step instructions for migrating from local ChromaDB to Azure AI Search for knowledge-base-agent workflows in **Ingenious**.

## Prerequisites

- Azure CLI installed and authenticated
- Azure OpenAI resource with separate embedding and chat deployments
- Azure subscription with appropriate permissions

## Minimal Azure Provisioning

### 1. Create Azure AI Search Service

```bash
# Create AI Search service (Basic tier - cheapest option after free tier)
# Note: Free tier is limited to one per subscription
az search service create \
  --name your-search-service \
  --resource-group your-rg-name \
  --sku basic \
  --location eastus
```

### 2. Get Search Service Keys

```bash
# Get admin keys for the search service
az search admin-key show \
  --service-name your-search-service \
  --resource-group your-rg-name
```

### 3. Create Required Azure OpenAI Deployments

Azure AI Search requires separate deployments for embeddings and generation:

```bash
# Create embedding deployment (required for vector search)
az cognitiveservices account deployment create \
  --name your-openai-resource \
  --resource-group your-rg-name \
  --deployment-name text-embedding-3-small-deployment \
  --model-name text-embedding-3-small \
  --model-version "1" \
  --model-format OpenAI \
  --sku-capacity 1 \
  --sku-name "Standard"

# Create or verify chat deployment exists
az cognitiveservices account deployment create \
  --name your-openai-resource \
  --resource-group your-rg-name \
  --deployment-name gpt-5-mini-deployment \
  --model-name gpt-5-mini \
  --model-version "2024-07-18" \
  --model-format OpenAI \
  --sku-capacity 1 \
  --sku-name "Standard"
```

## Environment Configuration

### CRITICAL: Model Configuration Requirements

**IMPORTANT**: Azure AI Search requires TWO separate model configurations - one for embeddings and one for chat/generation. Without both configured with different deployment names, you will receive the error "Embedding and chat deployments must not be the same".

### Update .env File

Migrate from local ChromaDB to Azure AI Search:

| Variable | Description | Example |
|----------|-------------|---------|
| **Model Configuration (REQUIRED)** | | |
| `INGENIOUS_MODELS__0__ROLE` | Must be set to "chat" | `chat` |
| `INGENIOUS_MODELS__0__DEPLOYMENT` | Chat model deployment | `gpt-5-mini-deployment` |
| `INGENIOUS_MODELS__1__ROLE` | Must be set to "embedding" | `embedding` |
| `INGENIOUS_MODELS__1__DEPLOYMENT` | Embedding model deployment | `text-embedding-3-small-deployment` |
| `KB_POLICY` | Backend selection policy | `azure_only` or `prefer_azure` |
| `INGENIOUS_AZURE_SEARCH_SERVICES__0__ENDPOINT` | Search service endpoint | `https://your-search-service.search.windows.net` |
| `INGENIOUS_AZURE_SEARCH_SERVICES__0__KEY` | Search admin key | `your-search-admin-key` |
| `INGENIOUS_AZURE_SEARCH_SERVICES__0__INDEX_NAME` | Search index name | `knowledge-base` |
| `INGENIOUS_AZURE_SEARCH_SERVICES__0__EMBEDDING_DEPLOYMENT_NAME` | Embedding model deployment | `text-embedding-3-small-deployment` |
| `INGENIOUS_AZURE_SEARCH_SERVICES__0__GENERATION_DEPLOYMENT_NAME` | Generation model deployment | `gpt-5-mini-deployment` |
| `INGENIOUS_AZURE_SEARCH_SERVICES__0__OPENAI_ENDPOINT` | Azure OpenAI endpoint | `https://eastus.api.cognitive.microsoft.com/` |
| `INGENIOUS_AZURE_SEARCH_SERVICES__0__OPENAI_KEY` | Azure OpenAI key | `your-openai-key` |
| `INGENIOUS_AZURE_SEARCH_SERVICES__0__OPENAI_VERSION` | API version | `2024-12-01-preview` |

### Complete .env Configuration

```bash
# Model 0: Chat/Generation model (REQUIRED)
INGENIOUS_MODELS__0__API_KEY=your-openai-api-key
INGENIOUS_MODELS__0__BASE_URL=https://your-region.api.cognitive.microsoft.com/
INGENIOUS_MODELS__0__MODEL=gpt-5-mini
INGENIOUS_MODELS__0__API_VERSION=2024-12-01-preview
INGENIOUS_MODELS__0__DEPLOYMENT=gpt-5-mini-deployment
INGENIOUS_MODELS__0__API_TYPE=rest
INGENIOUS_MODELS__0__ROLE=chat  # CRITICAL: Must be "chat"

# Model 1: Embedding model (REQUIRED for Azure AI Search)
INGENIOUS_MODELS__1__API_KEY=your-openai-api-key
INGENIOUS_MODELS__1__BASE_URL=https://your-region.api.cognitive.microsoft.com/
INGENIOUS_MODELS__1__MODEL=text-embedding-3-small
INGENIOUS_MODELS__1__API_VERSION=2024-12-01-preview
INGENIOUS_MODELS__1__DEPLOYMENT=text-embedding-3-small-deployment
INGENIOUS_MODELS__1__API_TYPE=rest
INGENIOUS_MODELS__1__ROLE=embedding  # CRITICAL: Must be "embedding"

# Knowledge base policy - choose one:
KB_POLICY=azure_only          # Use only Azure AI Search (strict)
# KB_POLICY=prefer_azure      # Prefer Azure, fallback to local ChromaDB
# KB_POLICY=prefer_local      # Prefer local ChromaDB, fallback to Azure
# KB_POLICY=local_only        # Use only local ChromaDB

# Optional: Enable fallback when Azure returns empty results
KB_FALLBACK_ON_EMPTY=true

# Knowledge base search parameters
KB_TOPK_DIRECT=3              # Number of results for direct mode
KB_TOPK_ASSIST=5              # Number of results for assist mode
KB_MODE=direct                # Search mode: direct or assist

# Azure AI Search Service Configuration
INGENIOUS_AZURE_SEARCH_SERVICES__0__ENDPOINT=https://your-search-service.search.windows.net
INGENIOUS_AZURE_SEARCH_SERVICES__0__KEY=your-search-admin-key
INGENIOUS_AZURE_SEARCH_SERVICES__0__INDEX_NAME=knowledge-base

# Note: The embedding and generation deployments are now configured via INGENIOUS_MODELS above
# These Azure Search specific settings are no longer required for deployments
```

## Create Search Index and Upload Documents

### 1. Create Search Index Schema

**IMPORTANT**: The index MUST include a `vector` field for Azure AI Search to work with the knowledge-base-agent. Without this field, you will get "Unknown field 'vector' in vector field list" error.

Create a search index with vector support:

```bash
# Create index schema file with vector field
cat > index_schema.json << 'EOF'
{
  "name": "knowledge-base",
  "fields": [
    {
      "name": "id",
      "type": "Edm.String",
      "key": true,
      "searchable": false,
      "filterable": true,
      "retrievable": true,
      "sortable": false,
      "facetable": false
    },
    {
      "name": "content",
      "type": "Edm.String",
      "searchable": true,
      "filterable": false,
      "retrievable": true,
      "sortable": false,
      "facetable": false
    },
    {
      "name": "title",
      "type": "Edm.String",
      "searchable": true,
      "filterable": true,
      "retrievable": true,
      "sortable": true,
      "facetable": false
    },
    {
      "name": "vector",
      "type": "Collection(Edm.Single)",
      "searchable": true,
      "retrievable": false,
      "dimensions": 1536,
      "vectorSearchProfile": "vector-profile"
    }
  ],
  "vectorSearch": {
    "algorithms": [
      {
        "name": "vector-algorithm",
        "kind": "hnsw",
        "hnswParameters": {
          "metric": "cosine",
          "m": 4,
          "efConstruction": 400,
          "efSearch": 500
        }
      }
    ],
    "profiles": [
      {
        "name": "vector-profile",
        "algorithm": "vector-algorithm"
      }
    ]
  },
  "semantic": {
    "defaultConfiguration": "default",
    "configurations": [
      {
        "name": "default",
        "prioritizedFields": {
          "titleField": {
            "fieldName": "title"
          },
          "prioritizedContentFields": [
            {
              "fieldName": "content"
            }
          ]
        }
      }
    ]
  }
}
EOF

# Create the index
curl -X PUT "https://your-search-service.search.windows.net/indexes/knowledge-base?api-version=2024-05-01-preview" \
  -H "Content-Type: application/json" \
  -H "api-key: your-search-admin-key" \
  -d @index_schema.json
```

### 2. Generate Embeddings and Upload Documents

**IMPORTANT**: Documents must include vector embeddings generated using your embedding deployment.

```python
# generate_embeddings.py
from openai import AzureOpenAI
import json

client = AzureOpenAI(
    api_key="your-openai-api-key",
    api_version="2024-12-01-preview",
    azure_endpoint="https://your-region.api.cognitive.microsoft.com/"
)

documents = [
    {
        "id": "1",
        "title": "Ingenious Setup Guide",
        "content": "Ingenious is a multi-agent AI framework that allows you to quickly set up APIs for AI agents."
    },
    {
        "id": "2",
        "title": "Azure Integration Guide",
        "content": "Ingenious supports Azure SQL, Cosmos DB, Azure Blob Storage, and Azure AI Search."
    }
]

# Generate embeddings
for doc in documents:
    response = client.embeddings.create(
        input=doc["content"],
        model="text-embedding-3-small-deployment"  # Your embedding deployment
    )
    doc["vector"] = response.data[0].embedding
    print(f"Generated embedding for document {doc['id']}")

with open("documents_with_embeddings.json", "w") as f:
    json.dump({"value": documents}, f)
```

Run the script and upload:

```bash
# Install OpenAI client
uv add openai

# Generate embeddings
uv run python generate_embeddings.py

# Upload documents with embeddings to the index
curl -X POST "https://your-search-service.search.windows.net/indexes/knowledge-base/docs/index?api-version=2024-05-01-preview" \
  -H "Content-Type: application/json" \
  -H "api-key: your-search-admin-key" \
  -d @documents_with_embeddings.json
```

## Policy Configuration

Azure AI Search supports flexible backend selection policies:

### KB_POLICY Options

- **azure_only**: Use only Azure AI Search (strict mode)
  - Fails if Azure is misconfigured or unavailable
  - Recommended for production environments

- **prefer_azure**: Prefer Azure AI Search, fallback to local ChromaDB
  - Attempts Azure first, falls back to local on failure
  - Good for development/testing environments

- **prefer_local**: Prefer local ChromaDB, fallback to Azure AI Search
  - Uses local ChromaDB first, Azure as backup
  - Useful during development phase

- **local_only**: Use only local ChromaDB
  - Ignores Azure configuration entirely
  - Development mode

## Verification

### 1. Validate Configuration

```bash
uv run ingen validate
```

Expected output: `All validations passed! Your Ingenious setup is ready.`

### 2. Start Server with Policy

```bash
# For Azure AI Search
export KB_POLICY=prefer_azure
uv run ingen serve --port 8000

# For local ChromaDB
export KB_POLICY=local_only
uv run ingen serve --port 8000
```

### 3. Health Check

```bash
curl http://localhost:8000/api/v1/health
```

### 4. Test Knowledge Base Agent

```bash
# Test knowledge-base-agent workflow
echo '{
  "user_prompt": "Search for documentation about setup",
  "conversation_flow": "knowledge-base-agent"
}' > test_knowledge_azure.json

curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d @test_knowledge_azure.json
```

Expected successful response with Azure AI Search results from your uploaded documents.

## Migration Strategies

### Strategy 1: Direct Migration (azure_only)

For immediate production deployment:

```bash
# Set strict Azure-only policy
KB_POLICY=azure_only

# Ensure all Azure AI Search configuration is complete
# Upload your existing knowledge base documents to Azure AI Search
# Test thoroughly before going live
```

### Strategy 2: Gradual Migration (prefer_azure)

For safer migration with fallback:

```bash
# Set prefer Azure with fallback
KB_POLICY=prefer_azure
KB_FALLBACK_ON_EMPTY=true

# Keep existing .tmp/knowledge_base/ directory as backup
# Azure AI Search will be tried first, local ChromaDB as fallback
# Gradually move content to Azure AI Search
```

### Strategy 3: Hybrid Approach (prefer_local)

For development with Azure testing:

```bash
# Set prefer local with Azure backup
KB_POLICY=prefer_local

# Keep developing with local ChromaDB
# Use Azure AI Search for testing production scenarios
```

## Troubleshooting

### Deployment Configuration Issues

**Error**: "Embedding and chat deployments must not be the same"

**Solution**: You must configure TWO separate models in your .env file:
1. Model 0 (`INGENIOUS_MODELS__0__*`) with `ROLE=chat` for generation
2. Model 1 (`INGENIOUS_MODELS__1__*`) with `ROLE=embedding` for embeddings

Both must have different deployment names. Without both models configured, the system will try to use the same deployment for both purposes and fail.

**Error**: "Unknown field 'vector' in vector field list"

**Solution**: Your index schema is missing the vector field. Recreate the index with the proper schema including a `vector` field of type `Collection(Edm.Single)` with 1536 dimensions as shown above

```bash
# Verify deployments are different
az cognitiveservices account deployment list \
  --name your-openai-resource \
  --resource-group your-rg-name \
  --output table
```

### Index Not Found Issues

**Error**: "The index 'your-index-name' was not found"

**Solution**:
1. Create the index using the REST API as shown above
2. Verify index exists:
   ```bash
   curl "https://your-search-service.search.windows.net/indexes/knowledge-base?api-version=2023-11-01" \
     -H "api-key: your-search-admin-key"
   ```

### Connection Issues

- Verify Azure AI Search service is running and accessible
- Check admin key is correct (not query key)
- Ensure search service endpoint format is correct
- Confirm network connectivity to Azure

### Policy Fallback Issues

If Azure fails but local fallback doesn't work:
- Check `.tmp/knowledge_base/` directory exists with documents
- Verify ChromaDB dependencies are installed
- Ensure KB_FALLBACK_ON_EMPTY=true for prefer_azure policy

## Cost Optimization

### Azure AI Search Pricing

- **Free Tier**: One per subscription, basic search capabilities
- **Basic Tier**: ~$15/month, 2GB storage, includes semantic search
- **Standard S1**: ~$250/month, production-grade with high availability

### Azure OpenAI Deployments

- **text-embedding-3-small**: ~$0.00002 per 1K tokens
- **gpt-5-mini**: ~$0.000075 per 1K tokens (generation)

Total minimal cost for light usage: ~$15-20/month with Basic search tier.

## Advanced Features

When properly configured, Azure AI Search provides:

- **Semantic Search**: Natural language understanding for better relevance
- **Vector Search**: Embedding-based similarity search
- **Hybrid Search**: Combines keyword and vector search
- **Dynamic Alpha Tuning (DAT)**: Optimizes search result fusion
- **Reranking**: Improves result ordering with semantic models

For local development setup, see the [Getting Started Guide](../getting-started.md).
