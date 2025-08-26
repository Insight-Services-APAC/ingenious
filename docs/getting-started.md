# Quick Start Guide

Get up and running in 5 minutes with Azure OpenAI!

## Prerequisites

- Python 3.13 or higher (required — earlier versions are not supported)
- Azure OpenAI resource with at least one **chat** model deployment and one **embedding** model deployment
- (Optional) Azure AI Search, Azure SQL, and Azure Storage if you want the full cloud setup
- [uv package manager](https://docs.astral.sh/uv/)

---

## 5-Minute Setup

### 1) Install and Initialize

```bash
# Navigate to your desired project directory first
cd /path/to/your/project

# Set up the uv project
uv init

# Choose installation based on features needed
uv add "ingenious[azure-full]"   # Recommended: Full Azure integration (core, auth, azure, ai, database, ui)
# OR
uv add "ingenious[standard]"     # For local testing: includes SQL agent support (core, auth, ai, database)

# Initialize project template in the current directory (adds sample workflows like bike-insights)
uv run ingen init
```

---

### 2) Configure Credentials (.env)

Create a `.env` file **in the project root** and paste the environment example below. Replace the placeholders with your real values.

!!! important
    See the environment example below.

#### 📄 Environment example (`.env`)

```bash
# ---------- Azure OpenAI ----------
AZURE_OPENAI_ENDPOINT="https://your-aoai-resource.openai.azure.com/"
AZURE_OPENAI_KEY="YOUR_AZURE_OPENAI_KEY"
AZURE_OPENAI_API_VERSION="2024-12-01-preview"
AZURE_OPENAI_GENERATION_DEPLOYMENT="gpt-4.1-mini"
AZURE_OPENAI_EMBEDDING_DEPLOYMENT="text-embedding-3-small"

# Ingenious model slots (must be token auth)
INGENIOUS_MODELS__0__MODEL="gpt-4.1-mini"
INGENIOUS_MODELS__0__API_TYPE="rest"
INGENIOUS_MODELS__0__API_VERSION="${AZURE_OPENAI_API_VERSION}"
INGENIOUS_MODELS__0__DEPLOYMENT="${AZURE_OPENAI_GENERATION_DEPLOYMENT}"
INGENIOUS_MODELS__0__API_KEY="${AZURE_OPENAI_KEY}"
INGENIOUS_MODELS__0__BASE_URL="${AZURE_OPENAI_ENDPOINT}"
INGENIOUS_MODELS__0__AUTHENTICATION_METHOD="token"

INGENIOUS_MODELS__1__MODEL="text-embedding-3-small"
INGENIOUS_MODELS__1__API_TYPE="rest"
INGENIOUS_MODELS__1__API_VERSION="${AZURE_OPENAI_API_VERSION}"
INGENIOUS_MODELS__1__DEPLOYMENT="${AZURE_OPENAI_EMBEDDING_DEPLOYMENT}"
INGENIOUS_MODELS__1__API_KEY="${AZURE_OPENAI_KEY}"
INGENIOUS_MODELS__1__BASE_URL="${AZURE_OPENAI_ENDPOINT}"
INGENIOUS_MODELS__1__AUTHENTICATION_METHOD="token"

INGENIOUS_CHAT_HISTORY__MEMORY_PATH="./.tmp"

# ---------- Azure AI Search (BASE ONLY) ----------
AZURE_SEARCH_ENDPOINT="https://your-search-service.search.windows.net"
AZURE_SEARCH_KEY="YOUR_AZURE_SEARCH_API_KEY"
AZURE_SEARCH_INDEX_NAME="your-index-name"
AZURE_SEARCH_SEMANTIC_CONFIG="some-semantic-config"

INGENIOUS_AZURE_SEARCH_SERVICES__0__SERVICE="default"
INGENIOUS_AZURE_SEARCH_SERVICES__0__ENDPOINT="${AZURE_SEARCH_ENDPOINT}"
INGENIOUS_AZURE_SEARCH_SERVICES__0__KEY="${AZURE_SEARCH_KEY}"
INGENIOUS_AZURE_SEARCH_SERVICES__0__INDEX_NAME="${AZURE_SEARCH_INDEX_NAME}"

# (optional tuning; keep if you use semantic)
INGENIOUS_AZURE_SEARCH_SERVICES__0__USE_SEMANTIC_RANKING="1"
INGENIOUS_AZURE_SEARCH_SERVICES__0__SEMANTIC_CONFIGURATION_NAME="your-semantic-config"
INGENIOUS_AZURE_SEARCH_SERVICES__0__ID_FIELD="id"
INGENIOUS_AZURE_SEARCH_SERVICES__0__CONTENT_FIELD="content"
INGENIOUS_AZURE_SEARCH_SERVICES__0__VECTOR_FIELD="vector"
INGENIOUS_AZURE_SEARCH_SERVICES__0__TOP_K_RETRIEVAL="5"
INGENIOUS_AZURE_SEARCH_SERVICES__0__TOP_N_FINAL="10"

# (optional; harmless if present)
INGENIOUS_SEARCH__PROVIDER="azure"
INGENIOUS_SEARCH__POLICY="azure_only"

# ---------- KB tuning ----------
KB_MODE="direct"
KB_TOP_K="5"
KB_USE_SEMANTIC_RANKING="1"
KB_POLICY="azure_only"
KB_WRITE_CONFIG_SNAPSHOT="1"

# ---------- Chat history (Azure SQL) ----------
# Keep on ONE line; quoting protects special chars
AZURE_SQL_CONNECTION_STRING="Driver={ODBC Driver 18 for SQL Server};Server=tcp:yourserver.database.windows.net,1433;Database=yourdatabase;Uid=your-username;Pwd=YOUR_STRONG_PASSWORD;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
INGENIOUS_CHAT_HISTORY__DATABASE_TYPE="azuresql"
INGENIOUS_CHAT_HISTORY__DATABASE_NAME="yourdatabase"
INGENIOUS_CHAT_HISTORY__DATABASE_CONNECTION_STRING="${AZURE_SQL_CONNECTION_STRING}"

# ---------- Azure Blob ----------
AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=yourstorageaccount;AccountKey=YOUR_STORAGE_ACCOUNT_KEY;EndpointSuffix=core.windows.net"

AZURE_STORAGE_REVISIONS_URL="https://yourstorageaccount.blob.core.windows.net/prompts/"
INGENIOUS_FILE_STORAGE__REVISIONS__ENABLE="true"
INGENIOUS_FILE_STORAGE__REVISIONS__STORAGE_TYPE="azure"
INGENIOUS_FILE_STORAGE__REVISIONS__CONTAINER_NAME="prompts"
INGENIOUS_FILE_STORAGE__REVISIONS__PATH="ingenious-files"
INGENIOUS_FILE_STORAGE__REVISIONS__ADD_SUB_FOLDERS="true"
INGENIOUS_FILE_STORAGE__REVISIONS__URL="${AZURE_STORAGE_REVISIONS_URL}"
INGENIOUS_FILE_STORAGE__REVISIONS__TOKEN="${AZURE_STORAGE_CONNECTION_STRING}"
INGENIOUS_FILE_STORAGE__REVISIONS__AUTHENTICATION_METHOD="token"

AZURE_STORAGE_DATA_URL="https://yourstorageaccount.blob.core.windows.net/data/"
INGENIOUS_FILE_STORAGE__DATA__ENABLE="true"
INGENIOUS_FILE_STORAGE__DATA__STORAGE_TYPE="azure"
INGENIOUS_FILE_STORAGE__DATA__CONTAINER_NAME="data"
INGENIOUS_FILE_STORAGE__DATA__PATH="ingenious-files"
INGENIOUS_FILE_STORAGE__DATA__ADD_SUB_FOLDERS="true"
INGENIOUS_FILE_STORAGE__DATA__URL="${AZURE_STORAGE_DATA_URL}"
INGENIOUS_FILE_STORAGE__DATA__TOKEN="${AZURE_STORAGE_CONNECTION_STRING}"
INGENIOUS_FILE_STORAGE__DATA__AUTHENTICATION_METHOD="token"

# ---------- Web ----------
INGENIOUS_WEB_CONFIGURATION__IP_ADDRESS="0.0.0.0"
INGENIOUS_WEB_CONFIGURATION__PORT="8080"

# ---------- Debug (optional) ----------
DEBUG_AZURE_CONFIG="1"
```

!!! tip
    Replace the placeholder values (e.g., `YOUR_AZURE_OPENAI_KEY`) with your own. The example uses quotes for safety; quoting is optional unless your value contains spaces or special characters.

---

### 3) Validate Configuration

```bash
uv run ingen validate  # Check configuration before starting
```

**If validation fails with port conflicts:**
Change `INGENIOUS_WEB_CONFIGURATION__PORT` in your `.env` (see the environment example above), then re-run:

```bash
uv run ingen validate
```

!!! warning "BREAKING CHANGE"
    Ingenious now uses **pydantic-settings** for configuration via environment variables.
    Legacy YAML configuration files (`config.yml`, `profiles.yml`) are **no longer supported** and must be migrated to environment variables with `INGENIOUS_` prefixes. Use the migration script:

    ```bash
    uv run python scripts/migrate_config.py --yaml-file config.yml --output .env
    uv run python scripts/migrate_config.py --yaml-file profiles.yml --output .env.profiles
    ```

---

### 4) Start the Server

```bash
# Start server on port 8000 (recommended for development)
uv run ingen serve --port 8000

# Additional options:
# --host 0.0.0.0         # Bind host (default: 0.0.0.0)
# --port                 # Port to bind (default: 80 or $WEB_PORT env var)
# --config config.yml    # Legacy config file (deprecated — use environment variables)
# --profile production   # Legacy profile (deprecated — use environment variables)
```

---

### 5) Verify Health

```bash
# Check server health
curl http://localhost:8000/api/v1/health
```

---

## Test the Core Workflows

Create test files to avoid shell-escaping issues:

```bash
# Classification
cat > test_classification.json <<'JSON'
{
  "user_prompt": "Analyze this customer feedback: Great product",
  "conversation_flow": "classification-agent"
}
JSON

# Knowledge base (minimal)
cat > test_knowledge.json <<'JSON'
{
  "user_prompt": "Search for documentation about setup",
  "conversation_flow": "knowledge-base-agent"
}
JSON

# Knowledge base (with top_k control)
cat > test_knowledge_topk.json <<'JSON'
{
  "user_prompt": "Search for documentation about setup",
  "conversation_flow": "knowledge-base-agent",
  "kb_top_k": 3
}
JSON

# SQL manipulation (uses local SQLite by default unless you configured Azure SQL)
cat > test_sql.json <<'JSON'
{
  "user_prompt": "Show me all tables in the database",
  "conversation_flow": "sql-manipulation-agent"
}
JSON

# Run tests
curl -sS -X POST http://localhost:8000/api/v1/chat -H "Content-Type: application/json" -d @test_classification.json
curl -sS -X POST http://localhost:8000/api/v1/chat -H "Content-Type: application/json" -d @test_knowledge.json
curl -sS -X POST http://localhost:8000/api/v1/chat -H "Content-Type: application/json" -d @test_knowledge_topk.json
curl -sS -X POST http://localhost:8000/api/v1/chat -H "Content-Type: application/json" -d @test_sql.json
```

**Expected Responses**:

- **classification-agent**: JSON with message analysis and categories
- **knowledge-base-agent**: JSON with relevant info retrieved from **Azure AI Search** (or a clear message if your index is empty/misconfigured). For local-only mode (`KB_POLICY=local_only`), results come from the local store (make sure you've loaded documents).
- **sql-manipulation-agent**: JSON with query results or confirmation

**Common KB Misconfigurations**:

- `PreflightError: [azure_search] policy: Azure Search is required…`
  → Ensure Azure Search is configured as in the environment example above and the `INGENIOUS_AZURE_SEARCH_SERVICES__0__...` block is present.
- 404/401/403 from Azure Search GET calls
  → Check `INDEX_NAME`, `ENDPOINT`, and `KEY`.

---

## Test the Template Workflow: `bike-insights`

!!! note
    The `bike-insights` workflow is part of the project template generated by `uv run ingen init`.

**Recommended (use `parameters` field to avoid JSON-in-JSON quoting):**

```bash
cat > test_bike_insights.json <<'JSON'
{
  "user_prompt": "Analyze these store sales and summarize insights.",
  "conversation_flow": "bike-insights",
  "parameters": {
    "revision_id": "test-v1",
    "identifier": "test-001",
    "stores": [
      {
        "name": "Test Store",
        "location": "NSW",
        "bike_sales": [
          {
            "product_code": "MB-TREK-2021-XC",
            "quantity_sold": 2,
            "sale_date": "2023-04-01",
            "year": 2023,
            "month": "April",
            "customer_review": { "rating": 4.5, "comment": "Great bike" }
          }
        ],
        "bike_stock": []
      }
    ]
  }
}
JSON

curl -sS -X POST http://localhost:8000/api/v1/chat -H "Content-Type: application/json" -d @test_bike_insights.json
```

---

## Workflow Categories

### Core Library Workflows (Always Available)

- `classification-agent` — Text classification and routing
- `knowledge-base-agent` — Knowledge retrieval (**defaults to Azure AI Search**). Local ChromaDB supported with `KB_POLICY=local_only`/`prefer_local` (install `chromadb`).
- `sql-manipulation-agent` — Execute SQL queries from natural language (uses local SQLite by default unless Azure SQL is configured)

!!! info
    Both hyphenated (`classification-agent`) and underscored (`classification_agent`) names are supported.

### Template Workflows (Created by `ingen init`)

- `bike-insights` — Multi-agent example for sales analysis (**only after `ingen init`**)

---

## Troubleshooting

- See the [detailed troubleshooting guide](docs/getting-started/troubleshooting.md) for port conflicts, configuration errors, and workflow issues.
- **Azure AI Search sanity check** (replace placeholders):
  ```bash
  curl -sD- -H "api-key: <your-search-key>"     "https://<your-service>.search.windows.net/indexes/<your-index>?api-version=2023-11-01"
  # Expect HTTP/1.1 200 OK
  ```

---

## Security Notes

- Do **NOT** commit `.env` files to source control.
- Redact secrets in logs. Avoid printing `api_key`, `key`, `Authorization`, `password`, `token`, etc.
- Rotate keys if accidentally exposed.

---

## Documentation

For detailed documentation, see the [docs](https://insight-services-apac.github.io/ingenious/).

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](https://github.com/Insight-Services-APAC/ingenious/blob/main/CONTRIBUTING.md).

## License

This project is licensed under the terms specified in the [LICENSE](https://github.com/Insight-Services-APAC/ingenious/blob/main/LICENSE) file.
