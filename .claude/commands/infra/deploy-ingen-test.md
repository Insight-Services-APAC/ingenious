# Deploy to ingen-test Resource Group

Deploy SoCa or Prompt Tuner applications to Azure using the ingen-test resource group.

## Instructions

1. **Determine which application to deploy** based on user input:
   - `soca` - Deploy SoCa application
   - `prompt-tuner` - Deploy Prompt Tuner application

2. **Resource Group**: Always use `ingen-test`. Do NOT create or use any other resource group.

3. **Resource Tagging**: Apply appropriate tags to all resources:
   - For SoCa: `app=soca`
   - For Prompt Tuner: `app=prompt-tuner`

4. **Provisioning Rules**:
   - Only provision resources if they don't already exist
   - Use the CHEAPEST tier available for all resources:
     - Static Web Apps: Free tier
     - Container Apps: Consumption plan (minReplicas=1, maxReplicas=3)
     - Container Apps Environment: Consumption workload profile
     - Container Registry: Basic tier

5. **Credentials**: Get credentials from `CREDENTIALS.md` at the repository root. DO NOT hardcode credentials in commands.

6. **Deployment Steps**:

### For SoCa:

```bash
# Check if resources exist
az staticwebapp show --name soca-frontend --resource-group ingen-test 2>/dev/null || \
  az staticwebapp create --name soca-frontend --resource-group ingen-test --location "East Asia" --sku Free --tags app=soca

# Build and deploy frontend
cd soca/frontend
npm run build
SOCA_TOKEN=$(az staticwebapp secrets list --name soca-frontend --resource-group ingen-test --query "properties.apiKey" -o tsv)
npx @azure/static-web-apps-cli deploy ./dist --deployment-token "$SOCA_TOKEN" --env production

# Deploy backend to Container Apps
cd ../backend
az containerapp up --name soca-backend --resource-group ingen-test --environment soca-env --source . --tags app=soca

# CRITICAL: Set environment variables after deployment
# Note: `az containerapp up` resets environment variables, so this step is required
# Get Cosmos DB key
COSMOS_KEY=$(az cosmosdb keys list --name ingen-test-cosmos --resource-group ingen-test --type keys --query "primaryMasterKey" -o tsv)

# Set all required environment variables (get SOCA_ADMIN_EMAIL and SOCA_ADMIN_PASSWORD from CREDENTIALS.md)
az containerapp update --name soca-backend --resource-group ingen-test \
  --min-replicas 1 --max-replicas 3 \
  --set-env-vars \
    "SOCA_AUTH_ENABLED=true" \
    "SOCA_ADMIN_EMAIL=<from-credentials-md>" \
    "SOCA_ADMIN_PASSWORD=<from-credentials-md>" \
    "SOCA_JWT_SECRET=soca-jwt-secret-ingen-test-$(date +%Y)" \
    "SOCA_COSMOS_URI=https://ingen-test-cosmos.documents.azure.com:443/" \
    "SOCA_COSMOS_KEY=$COSMOS_KEY" \
    "SOCA_COSMOS_DATABASE=soca"
```

**Required SoCa Backend Environment Variables:**
| Variable | Description | Source |
|----------|-------------|--------|
| SOCA_AUTH_ENABLED | Enable authentication | `true` |
| SOCA_ADMIN_EMAIL | Admin login email | CREDENTIALS.md |
| SOCA_ADMIN_PASSWORD | Admin login password | CREDENTIALS.md |
| SOCA_JWT_SECRET | JWT signing secret | Generate unique value |
| SOCA_COSMOS_URI | Cosmos DB endpoint | Azure portal or CLI |
| SOCA_COSMOS_KEY | Cosmos DB primary key | `az cosmosdb keys list` |
| SOCA_COSMOS_DATABASE | Cosmos DB database name | `soca` |

### For Prompt Tuner:

```bash
# Check if resources exist
az staticwebapp show --name prompt-tuner-frontend --resource-group ingen-test 2>/dev/null || \
  az staticwebapp create --name prompt-tuner-frontend --resource-group ingen-test --location "East Asia" --sku Free --tags app=prompt-tuner

# Build and deploy frontend
cd ingen-prompt-tuner/frontend
npm run build
PT_TOKEN=$(az staticwebapp secrets list --name prompt-tuner-frontend --resource-group ingen-test --query "properties.apiKey" -o tsv)
npx @azure/static-web-apps-cli deploy ./dist --deployment-token "$PT_TOKEN" --env production

# Deploy backend to Container Apps
cd ../backend
az containerapp up --name prompttuner-backend --resource-group ingen-test --environment soca-env --source . --tags app=prompt-tuner

# CRITICAL: Set environment variables after deployment
# Note: `az containerapp up` resets environment variables, so this step is required
# Get Cosmos DB key (same as SoCa - shared database)
COSMOS_KEY=$(az cosmosdb keys list --name ingen-test-cosmos --resource-group ingen-test --type keys --query "primaryMasterKey" -o tsv)

# Set all required environment variables (get PT_ADMIN_EMAIL and PT_ADMIN_PASSWORD from CREDENTIALS.md)
az containerapp update --name prompttuner-backend --resource-group ingen-test \
  --min-replicas 1 --max-replicas 3 \
  --set-env-vars \
    "PT_AUTH_ENABLED=true" \
    "PT_ADMIN_EMAIL=<from-credentials-md>" \
    "PT_ADMIN_PASSWORD=<from-credentials-md>" \
    "PT_JWT_SECRET=prompttuner-jwt-secret-ingen-test-$(date +%Y)" \
    "PT_COSMOS_ENDPOINT=https://ingen-test-cosmos.documents.azure.com:443/" \
    "PT_COSMOS_KEY=$COSMOS_KEY" \
    "PT_COSMOS_DATABASE=soca" \
    "PT_COSMOS_CONTAINER=traces"
```

**Required Prompt Tuner Backend Environment Variables:**
| Variable | Description | Source |
|----------|-------------|--------|
| PT_AUTH_ENABLED | Enable authentication | `true` |
| PT_ADMIN_EMAIL | Admin login email | CREDENTIALS.md |
| PT_ADMIN_PASSWORD | Admin login password | CREDENTIALS.md |
| PT_JWT_SECRET | JWT signing secret | Generate unique value |
| PT_COSMOS_ENDPOINT | Cosmos DB endpoint | Azure portal or CLI |
| PT_COSMOS_KEY | Cosmos DB primary key | `az cosmosdb keys list` |
| PT_COSMOS_DATABASE | Cosmos DB database name | `soca` |
| PT_COSMOS_CONTAINER | Cosmos DB container for traces | `traces` |

## Verification

After deployment, verify the applications are running:

```bash
# Check frontend URLs
az staticwebapp show --name soca-frontend --resource-group ingen-test --query defaultHostname -o tsv
az staticwebapp show --name prompt-tuner-frontend --resource-group ingen-test --query defaultHostname -o tsv

# Check backend health
curl https://soca-backend.kindsea-9799773a.australiaeast.azurecontainerapps.io/health
curl https://prompttuner-backend.kindsea-9799773a.australiaeast.azurecontainerapps.io/health

# Test login endpoints (use credentials from CREDENTIALS.md)
curl -X POST https://soca-backend.kindsea-9799773a.australiaeast.azurecontainerapps.io/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"<from-credentials-md>","password":"<from-credentials-md>"}'

curl -X POST https://prompttuner-backend.kindsea-9799773a.australiaeast.azurecontainerapps.io/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"<from-credentials-md>","password":"<from-credentials-md>"}'
```

## Troubleshooting

### Common Issues

1. **"Invalid credentials" on login**
   - Cause: Missing `*_ADMIN_EMAIL` and `*_ADMIN_PASSWORD` environment variables
   - Fix: Run `az containerapp update` with the credentials from CREDENTIALS.md

2. **500 errors / CORS errors after login**
   - Cause: Missing database credentials (e.g., `SOCA_COSMOS_KEY`)
   - Fix: Add the Cosmos DB key using `az containerapp update --set-env-vars`

3. **"ModuleNotFoundError: No module named 'prompt_tuner'"**
   - Cause: Dockerfile has wrong module name
   - Fix: Ensure Dockerfile CMD uses `ingen_prompt_tuner.main:app` not `prompt_tuner.main:app`

4. **Environment variables reset after deployment**
   - Cause: `az containerapp up` resets all environment variables
   - Fix: Always run `az containerapp update --set-env-vars` after `az containerapp up`

5. **"No test runs found" in Prompt Tuner**
   - Cause: Missing `PT_COSMOS_KEY` environment variable
   - Fix: Add Cosmos DB configuration (`PT_COSMOS_ENDPOINT`, `PT_COSMOS_KEY`, `PT_COSMOS_DATABASE`, `PT_COSMOS_CONTAINER`)

### Viewing Container Logs

```bash
# SoCa backend logs
az containerapp logs show --name soca-backend --resource-group ingen-test --tail 50

# Prompt Tuner backend logs
az containerapp logs show --name prompttuner-backend --resource-group ingen-test --tail 50
```

## Cost Optimization

- Static Web Apps Free tier: $0/month
- Container Apps Consumption: Pay only for active use (first 2M requests free)
- Container Registry Basic: ~$5/month
- Total estimated cost: <$10/month for light usage

## Arguments

Usage: `/deploy-ingen-test [soca|prompt-tuner|all]`

- `soca` - Deploy only SoCa
- `prompt-tuner` - Deploy only Prompt Tuner
- `all` - Deploy both applications
