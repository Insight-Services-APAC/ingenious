# Complete Azure Deployment Guide

This guide provides step-by-step instructions for moving from local development to production Azure deployment with **Azure SQL** and **Azure Blob Storage**.

## Prerequisites

- Azure CLI installed and authenticated
- Azure OpenAI resource (required)
- Azure subscription with appropriate permissions

## Quick Deploy with Bicep (Optional)

If you want to recreate the core Azure resources from this guide in a single step, use the Bicep template located at `infra/main.bicep`. The defaults match the resource names used throughout the documentation; override parameters as needed to avoid name collisions.

```bash
# Deploy (or update) resources into your resource group
az deployment group create \
  --resource-group your-rg-name \
  --template-file infra/main.bicep \
  --parameters sqlAdministratorPassword='YourStrongPassword!' \
               clientIpAddress=$(curl -s ipinfo.io/ip)

# Preview changes without applying
az deployment group what-if \
  --resource-group your-rg-name \
  --template-file infra/main.bicep \
  --parameters sqlAdministratorPassword='YourStrongPassword!'
```

## Minimal Azure Provisioning

### 1. Create Resource Group

```bash
# Check if resource group exists first
az group show --name your-rg-name 2>/dev/null ||
az group create --name your-rg-name --location eastus
```

### 2. Provision Azure SQL (Basic - 5 DTUs)

```bash
# Register the SQL resource provider if this subscription has never created SQL resources
if [ "$(az provider show --namespace Microsoft.Sql --query "registrationState" -o tsv 2>/dev/null)" != "Registered" ]; then
  az provider register --namespace Microsoft.Sql
fi

# Check if SQL Server exists first
SQL_EXISTS=$(az sql server show --name your-sql-server --resource-group your-rg-name 2>/dev/null)
if [ -z "$SQL_EXISTS" ]; then
  # Create SQL Server only if it doesn't exist
  SQL_PASSWORD=$(openssl rand -base64 32)
  az sql server create \
    --name your-sql-server \
    --resource-group your-rg-name \
    --location eastus2 \
    --admin-user adminuser \
    --admin-password "$SQL_PASSWORD"
  echo "SQL Password: $SQL_PASSWORD"
else
  echo "SQL Server already exists, skipping creation"
fi

# Create Database (Basic SKU - cheapest option)
az sql db create \
  --resource-group your-rg-name \
  --server your-sql-server \
  --name ingenious-db \
  --service-objective Basic

# Allow Azure services access
az sql server firewall-rule create \
  --resource-group your-rg-name \
  --server your-sql-server \
  --name AllowAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0

# Allow your IP (replace with your actual IP)
MY_IP=$(curl -s ipinfo.io/ip)
az sql server firewall-rule create \
  --resource-group your-rg-name \
  --server your-sql-server \
  --name AllowMyIP \
  --start-ip-address "$MY_IP" \
  --end-ip-address "$MY_IP"
```

### 3. Provision Azure Blob Storage

```bash
# Check if storage account exists first
STORAGE_EXISTS=$(az storage account show --name yourblobstorage --resource-group your-rg-name 2>/dev/null)
if [ -z "$STORAGE_EXISTS" ]; then
  # Create storage account (Standard_LRS - cheapest option)
  az storage account create \
    --name yourblobstorage \
    --resource-group your-rg-name \
    --location eastus2 \
    --sku Standard_LRS \
    --kind StorageV2
else
  echo "Storage account already exists, skipping creation"
fi

# Create prompts container
az storage container create \
  --account-name yourblobstorage \
  --name prompts \
  --auth-mode login
```

## Environment Configuration

### Transition from Local to Azure

When moving from local development to Azure, update your `.env` file with the following changes:

#### Local Development Configuration (Starting Point)
```bash
# Local SQLite database
INGENIOUS_CHAT_HISTORY__DATABASE_TYPE=sqlite
INGENIOUS_CHAT_HISTORY__DATABASE_PATH=./.tmp/chat_history.db

# Local file storage
INGENIOUS_FILE_STORAGE__REVISIONS__ENABLE=true
INGENIOUS_FILE_STORAGE__REVISIONS__STORAGE_TYPE=local
```

#### Azure Production Configuration (Target)
```bash
# Azure SQL Database for Chat History
INGENIOUS_CHAT_HISTORY__DATABASE_TYPE=azuresql
INGENIOUS_CHAT_HISTORY__DATABASE_CONNECTION_STRING=Driver={ODBC Driver 18 for SQL Server};Server=tcp:your-sql-server.database.windows.net,1433;Database=ingenious-db;Uid=adminuser;Pwd=YOUR_PASSWORD;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;
INGENIOUS_CHAT_HISTORY__DATABASE_NAME=ingenious-db

# Azure Blob Storage for prompt templates
INGENIOUS_FILE_STORAGE__REVISIONS__ENABLE=true
INGENIOUS_FILE_STORAGE__REVISIONS__STORAGE_TYPE=azure
INGENIOUS_FILE_STORAGE__REVISIONS__CONTAINER_NAME=prompts
INGENIOUS_FILE_STORAGE__REVISIONS__PATH=./
INGENIOUS_FILE_STORAGE__REVISIONS__URL=https://yourblobstorage.blob.core.windows.net
INGENIOUS_FILE_STORAGE__REVISIONS__TOKEN=DefaultEndpointsProtocol=https;AccountName=yourblobstorage;AccountKey=YOUR_KEY;EndpointSuffix=core.windows.net

# Production Security: Disable built-in workflows
INGENIOUS_CHAT_SERVICE__ENABLE_BUILTIN_WORKFLOWS=false
```

### Complete Environment Variable Reference

| Variable | Local Value | Azure Value | Description |
|----------|-------------|-------------|-------------|
| `INGENIOUS_CHAT_HISTORY__DATABASE_TYPE` | `sqlite` | `azuresql` | Database backend type |
| `INGENIOUS_CHAT_HISTORY__DATABASE_PATH` | `./.tmp/chat_history.db` | (remove) | Local SQLite path |
| `INGENIOUS_CHAT_HISTORY__DATABASE_CONNECTION_STRING` | (not needed) | `Driver={ODBC...}` | Azure SQL connection for chat history |
| `INGENIOUS_CHAT_HISTORY__DATABASE_NAME` | (not needed) | `ingenious-db` | Azure SQL database name for chat history |
| `INGENIOUS_FILE_STORAGE__REVISIONS__ENABLE` | `false` | `true` | Enable cloud file storage |
| `INGENIOUS_FILE_STORAGE__REVISIONS__STORAGE_TYPE` | `local` | `azure` | Storage backend type |
| `INGENIOUS_FILE_STORAGE__REVISIONS__CONTAINER_NAME` | (not needed) | `prompts` | Blob container name |
| `INGENIOUS_FILE_STORAGE__REVISIONS__PATH` | `./` | `./` | Blob prefix (keeps templates under templates/) |
| `INGENIOUS_FILE_STORAGE__REVISIONS__URL` | (not needed) | `https://...` | Storage account URL |
| `INGENIOUS_FILE_STORAGE__REVISIONS__TOKEN` | (not needed) | `DefaultEndpoints...` | Storage connection string |
| `INGENIOUS_CHAT_SERVICE__ENABLE_BUILTIN_WORKFLOWS` | `true` | `false` | Production security setting |

### Get Azure Resource Information

```bash
# Get storage account key
az storage account keys list \
  --account-name yourblobstorage \
  --resource-group your-rg-name \
  --output table

# Verify SQL server admin username (should match connection string)
az sql server show \
  --name your-sql-server \
  --resource-group your-rg-name \
  --query 'administratorLogin' \
  --output tsv

# Get SQL server FQDN for connection string
az sql server show \
  --name your-sql-server \
  --resource-group your-rg-name \
  --query 'fullyQualifiedDomainName' \
  --output tsv
```

## Upload Prompt Templates

Upload your prompt templates to the correct blob path:

```bash
# Upload templates for revision "quickstart-1"
for file in templates/prompts/quickstart-1/*.jinja; do
  filename=$(basename "$file")
  az storage blob upload \
    --account-name yourblobstorage \
    --container-name prompts \
    --name "templates/prompts/quickstart-1/$filename" \
    --file "$file" \
    --auth-mode key \
    --overwrite
done

# Alternative: upload the entire templates tree in one command while preserving folder structure
az storage blob upload-batch \
  --account-name yourblobstorage \
  --account-key "$(az storage account keys list --account-name yourblobstorage --resource-group your-rg-name --query '[0].value' -o tsv)" \
  --destination prompts \
  --destination-path templates \
  --source templates
```

## Azure Integration Verification

Once configuration is in place, validate that Azure SQL and Blob Storage are wired up end-to-end.

```bash
# 1. Start the server with authentication enabled
export PYTHONPATH=$(pwd):$PYTHONPATH
KB_POLICY=prefer_azure uv run ingen serve --port 8000

# 2. Health check (no auth required)
curl http://localhost:8000/api/v1/health

# 3. Exercise a workflow with Basic Auth (replace credentials with your own values)
AUTH_HEADER=$(echo -n 'admin:SuperSecurePassword!' | base64)
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $AUTH_HEADER" \
  -d @test_bike_insights.json

# 4. Confirm chat history rows landed in Azure SQL
uv run python <<PY
import pyodbc
conn = pyodbc.connect(
    "Driver={ODBC Driver 18 for SQL Server};"
    "Server=tcp:your-sql-server.database.windows.net,1433;"
    "Database=ingenious-db;Uid=adminuser;Pwd=YOUR_PASSWORD;"
    "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
)
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM chat_history")
print("chat_history rows:", cursor.fetchone()[0])
cursor.close()
conn.close()
PY

# 5. Verify prompts are being served from Azure Blob Storage
curl -H "Authorization: Basic $AUTH_HEADER" \
  http://localhost:8000/api/v1/prompts/list/quickstart-1
```

If the workflow succeeds, the SQL row count increases, and the prompt listing returns template filenames, the Azure SQL and Blob integrations are working.

## Production Security Configuration

### Disable Built-in Workflows (Recommended for Production)

For production deployments, you can disable the built-in workflows (`classification-agent`, `knowledge-base-agent`, `sql-manipulation-agent`) to expose only your custom workflows from `ingenious_extensions`:

```bash
# Add to your .env file for production security
INGENIOUS_CHAT_SERVICE__ENABLE_BUILTIN_WORKFLOWS=false
```

**Testing the Security Setting:**

```bash
# Test that built-in workflows are blocked (should return error)
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'username:password' | base64)" \
  -d '{"user_prompt": "Test", "conversation_flow": "classification-agent", "thread_id": "test"}'

# Expected error response:
# {"detail":"Built-in workflow 'classification-agent' is disabled. Set INGENIOUS_CHAT_SERVICE__ENABLE_BUILTIN_WORKFLOWS=true to enable built-in workflows, or use a custom workflow from ingenious_extensions."}

# Custom workflows still work:
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'username:password' | base64)" \
  -d '{"user_prompt": "Test", "conversation_flow": "your-custom-workflow", "thread_id": "test"}'
```

## Verification

### 1. Validate Configuration

```bash
uv run ingen validate
```

Expected output: `All validations passed! Your Ingenious setup is ready.`

### 2. Start Server

```bash
uv run ingen serve --port 8000
```

### 3. Health Check

```bash
curl http://localhost:8000/api/v1/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2025-08-29T06:06:02.916027",
  "response_time_ms": 2.06,
  "components": {
    "configuration": "ok",
    "profile": "ok"
  },
  "version": "1.0.0",
  "uptime": "available"
}
```

### 4. Test Workflow with Azure Integrations

```bash
# Test bike-insights workflow (requires prompt templates uploaded)
echo '{
  "user_prompt": "{\"revision_id\": \"quickstart-1\", \"identifier\": \"test-001\", \"stores\": [{\"name\": \"Test Store\", \"location\": \"NSW\", \"bike_sales\": [{\"product_code\": \"MB-TREK-2021-XC\", \"quantity_sold\": 2, \"sale_date\": \"2023-04-01\", \"year\": 2023, \"month\": \"April\", \"customer_review\": {\"rating\": 4.5, \"comment\": \"Great bike\"}}], \"bike_stock\": []}]}",
  "conversation_flow": "bike-insights"
}' > test_azure.json

curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d @test_azure.json
```

Successful response indicates:
- Azure SQL connection for chat history persistence
- Azure Blob prompt template loading
- Multi-agent workflow execution

## Troubleshooting

### SQL Connection Issues
- Verify firewall rules allow your IP
- Check connection string format
- Ensure database exists

### Blob Storage Issues
- Verify storage account key is correct
- Ensure prompt templates uploaded to correct path: `templates/prompts/{revision_id}/`
- Check container permissions

### Rate Limiting
Azure OpenAI free tier (S0) has token limits. Consider upgrading to Pay-as-you-go for production use.

## Cost Optimization

- **Azure SQL Basic (5 DTUs)**: ~$5/month
- **Storage Account (Standard_LRS)**: ~$0.02/GB/month
- **Azure OpenAI**: Pay per token usage

Total minimal cost: ~$5-10/month for light usage.

For detailed local setup, see the [Getting Started Guide](../getting-started.md).
