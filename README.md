# Insight Ingenious

[![Version](https://img.shields.io/badge/version-0.2.6-blue.svg)](https://github.com/Insight-Services-APAC/ingenious)
[![Python](https://img.shields.io/badge/python-3.13+-green.svg)](https://www.python.org/downloads/)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/Insight-Services-APAC/ingenious)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

Ingenious is a tool for quickly setting up APIs to interact with AI Agents. It features multi-agent conversation flows using Microsoft's AutoGen, JWT authentication, and supports both local development (SQLite, ChromaDB) and production Azure deployments (Azure OpenAI, Azure SQL, Cosmos DB, Azure AI Search, Azure Blob, Container Apps).

## Quick Start

Get up and running in 5 minutes with just an Azure OpenAI API key!

### Prerequisites
- Python 3.13 or higher (required - earlier versions are not supported)
- OpenAI or Azure OpenAI API credentials
- [uv package manager](https://docs.astral.sh/uv/)

**Flexible Architecture**: Ingenious supports both local development (SQLite, ChromaDB) and production Azure deployments (Azure SQL, Cosmos DB, Azure AI Search, Azure Blob, Container Apps). Start local, scale to Azure as needed.

### AI-Assisted Set Up (give this prompt to your preferred coding agent)

**WARNING: Audit ALL Azure CLI commands!**

```markdown
Follow all steps in [this guide](https://blog.insight-services-apac.dev/ingenious/getting-started/) and [this guide](https://blog.insight-services-apac.dev/ingenious/guides/complete-azure-deployment/).

Set up ingenious locally first and then migrate to Azure services as shown in the docs.

- Deploy only required resources at minimal cost.
- Use a new resource group: **<your-new-rg-name>**.
- For the SQL Server SKU choose Basic - 5 DTUs
- Azure CLI access is available.
```
### 5-Minute Setup

1. **Install and Initialize**:
    ```bash
    # Navigate to your desired project directory first
    cd /path/to/your/project

    # Set up the uv project
    uv init

    # Choose installation based on features needed:

    # Basic API server only (33 packages)
    uv add "ingenious"

    # Standard production setup with auth + AI + database (86 packages)
    uv add "ingenious[standard]"

    # Full Azure cloud integration (recommended for production)
    uv add "ingenious[azure-full]"

    # Everything including document processing and ML
    uv add "ingenious[full]"

    # Or build your own combination:
    # uv add "ingenious[core,auth,ai]"           # Basic AI workflows with auth
    # uv add "ingenious[ai,knowledge-base]"      # AI + vector search only
    # uv add "ingenious[azure,database]"         # Azure + database without AI

    # For nightly builds, add --index-url prefix:
    # uv add --index-url https://test.pypi.org/simple/ "ingenious[azure-full]"

    # Initialize project in the current directory
    uv run ingen init
    ```

2. **Configure Credentials**:
    Create a `.env` file with your Azure OpenAI credentials:
    ```bash
    # Create .env file in current directory
    touch .env

    # Edit .env file with your actual credentials
    ```

    **Required configuration (add to .env file)**:
    ```bash
    # Core AI Model Configuration (REQUIRED)
    INGENIOUS_MODELS__0__MODEL=gpt-4o-mini
    INGENIOUS_MODELS__0__API_TYPE=rest
    INGENIOUS_MODELS__0__API_VERSION=2024-12-01-preview
    INGENIOUS_MODELS__0__DEPLOYMENT=gpt-4o-mini-deployment
    INGENIOUS_MODELS__0__API_KEY=your-actual-api-key-here
    INGENIOUS_MODELS__0__BASE_URL=https://eastus.api.cognitive.microsoft.com/

    # For Azure OpenAI: Use the Cognitive Services endpoint format (not OpenAI endpoint)
    # CORRECT: https://eastus.api.cognitive.microsoft.com/
    # INCORRECT: https://your-resource.openai.azure.com/
    # For OpenAI (not Azure), use:
    # INGENIOUS_MODELS__0__BASE_URL=https://api.openai.com/v1
    # INGENIOUS_MODELS__0__API_VERSION=2024-02-01

    # Web Server Configuration (use different port if 80 conflicts)
    INGENIOUS_WEB_CONFIGURATION__PORT=8000
    INGENIOUS_WEB_CONFIGURATION__IP_ADDRESS=0.0.0.0
    INGENIOUS_WEB_CONFIGURATION__AUTHENTICATION__ENABLE=false

    # Chat Service Configuration (REQUIRED)
    INGENIOUS_CHAT_SERVICE__TYPE=multi_agent

    # Production: Disable built-in workflows (optional)
    # INGENIOUS_CHAT_SERVICE__ENABLE_BUILTIN_WORKFLOWS=false

    # Chat History Database (Local SQLite)
    INGENIOUS_CHAT_HISTORY__DATABASE_TYPE=sqlite
    INGENIOUS_CHAT_HISTORY__DATABASE_PATH=./.tmp/chat_history.db
    INGENIOUS_CHAT_HISTORY__MEMORY_PATH=./.tmp

    # Knowledge base configuration - local ChromaDB for development
    KB_POLICY=local_only
    KB_TOPK_DIRECT=3
    KB_TOPK_ASSIST=5
    KB_MODE=direct

    # SQL database configuration - local SQLite for development
    INGENIOUS_LOCAL_SQL_DB__DATABASE_PATH=./.tmp/sample_sql.db

    # Logging Configuration
    INGENIOUS_LOGGING__ROOT_LOG_LEVEL=info
    INGENIOUS_LOGGING__LOG_LEVEL=info
    ```

3. **Validate Configuration**:
    ```bash
    uv run ingen validate  # Check configuration before starting
    ```

    **Expected validation output**: You should see confirmation that your configuration is valid and a count of available workflows:
    - **Minimal install**: 0/3 workflows (requires `[ai]` group for workflow functionality)
    - **Standard install**: 3/4 workflows (classification-agent, sql-manipulation-agent working; knowledge-base-agent requires `[knowledge-base]` group)
    - **Azure-full install**: 4/4 workflows working (classification-agent, knowledge-base-agent, sql-manipulation-agent, and bike-insights after `ingen init`)

    **If validation fails with port conflicts**:
    ```bash
    # Find and kill process using port 8000 (recommended approach)
    lsof -ti:8000 | xargs kill -9
    uv run ingen validate

    # Alternative: Check if validation passes with different port
    INGENIOUS_WEB_CONFIGURATION__PORT=8001 uv run ingen validate

    # Or update your .env file before validating:
    echo "INGENIOUS_WEB_CONFIGURATION__PORT=8001" >> .env
    uv run ingen validate
    ```

    > **⚠️ NOTE**: Ingenious now uses **pydantic-settings** for configuration via environment variables. Legacy YAML files are no longer supported—define configuration through `INGENIOUS_*` environment variables or `.env` files (e.g., `INGENIOUS_MODELS__0__API_KEY`, `INGENIOUS_MODELS__0__BASE_URL`).

4. **Start the Server**:
    ```bash
    # REQUIRED: Use KB_POLICY=local_only for knowledge-base-agent to work with ChromaDB
    KB_POLICY=local_only uv run ingen serve --port 8000

    # Alternative: Start server without KB prefix (but knowledge-base-agent may not work)
    uv run ingen serve --port 8000

    # Note: Default port is 80, but port 8000 is recommended to avoid conflicts
    # Additional options:
    # --host 0.0.0.0         # Bind host (default: 0.0.0.0)
    # --port                 # Port to bind (default: 80 or $INGENIOUS_WEB_CONFIGURATION__PORT)
    ```

5. **Verify Health**:
    ```bash
    # Check server health (adjust port if different)
    curl http://localhost:8000/api/v1/health
    ```

    **Expected health response**: A JSON response indicating server status:
    ```json
    {
      "status": "healthy",
      "timestamp": "2025-08-29T01:15:30.830525",
      "response_time_ms": 1.4,
      "components": {"configuration": "ok", "profile": "ok"},
      "version": "1.0.0",
      "uptime": "available"
    }
    ```

6. **Test with Core Workflows**:

    Create test files to avoid JSON escaping issues:
    ```bash
    # Create test files for each workflow
    echo '{"user_prompt": "Analyze this customer feedback: Great product", "conversation_flow": "classification-agent"}' > test_classification.json
    echo '{"user_prompt": "Search for documentation about setup", "conversation_flow": "knowledge-base-agent"}' > test_knowledge.json
    echo '{"user_prompt": "Show me all tables in the database", "conversation_flow": "sql-manipulation-agent"}' > test_sql.json

    # Test each workflow
    curl -X POST http://localhost:8000/api/v1/chat -H "Content-Type: application/json" -d @test_classification.json
    curl -X POST http://localhost:8000/api/v1/chat -H "Content-Type: application/json" -d @test_knowledge.json
    curl -X POST http://localhost:8000/api/v1/chat -H "Content-Type: application/json" -d @test_sql.json
    ```

    **To populate knowledge base for testing** (optional but recommended):
    ```bash
    # Create sample knowledge base document for testing
    mkdir -p .tmp/knowledge_base
    cat > .tmp/knowledge_base/setup_guide.md << 'EOF'
    # Ingenious Setup Guide

    ## Quick Setup Instructions

    Ingenious is a multi-agent AI framework that allows you to quickly set up APIs for AI agents.

    ### Prerequisites
    - Python 3.13+
    - OpenAI API key or Azure OpenAI credentials
    - UV package manager

    ### Installation Steps
    1. Initialize UV project: `uv init`
    2. Install Ingenious: `uv add "ingenious[azure-full]"`
    3. Initialize project: `uv run ingen init`
    4. Configure environment variables in .env file
    5. Start server: `uv run ingen serve --port 8000`
    EOF

    # Now test knowledge-base-agent again to see populated results
    curl -X POST http://localhost:8000/api/v1/chat -H "Content-Type: application/json" -d @test_knowledge.json
    ```

**Expected Responses**:
- **Successful classification-agent response**: JSON with message analysis, sentiment scores, and topic categorization
- **Successful knowledge-base-agent response**: JSON with relevant information retrieved from local ChromaDB (with sample document, will contain setup instructions; without, may indicate empty knowledge base)
- **Successful sql-manipulation-agent response**: JSON with SQL query results showing database table information from local SQLite database (sample database includes `students_performance` table)

**Example successful responses**:
```bash
# classification-agent typical response format:
{"response": "Analysis: Positive sentiment (0.8/1.0)... Category: Product Feedback"}

# knowledge-base-agent with populated knowledge base:
{"response": "Based on the setup guide: Ingenious requires Python 3.13+..."}

# sql-manipulation-agent typical response:
{"response": "Found 3 tables in database: users, products, orders..."}
```

That's it! You should see a JSON response with AI analysis of the input.

**Next Steps - Test Additional Workflows**:

7. **Test bike-insights Workflow (Requires `ingen init` first)**:

    The `bike-insights` workflow is part of the project template and must be initialized first:
    ```bash
    # First initialize project to get bike-insights workflow
    uv run ingen init

    # Create bike-insights test data file
    # IMPORTANT: bike-insights requires JSON data in the user_prompt field (double-encoded JSON)
    printf '%s\n' '{
      "user_prompt": "{\"revision_id\": \"quickstart-1\", \"identifier\": \"test-001\", \"stores\": [{\"name\": \"Test Store\", \"location\": \"NSW\", \"bike_sales\": [{\"product_code\": \"MB-TREK-2021-XC\", \"quantity_sold\": 2, \"sale_date\": \"2023-04-01\", \"year\": 2023, \"month\": \"April\", \"customer_review\": {\"rating\": 4.5, \"comment\": \"Great bike\"}}], \"bike_stock\": []}]}",
      "conversation_flow": "bike-insights"
    }' > test_bike_insights.json

    # Test bike-insights workflow
    curl -X POST http://localhost:8000/api/v1/chat -H "Content-Type: application/json" -d @test_bike_insights.json
    ```

    **Expected bike-insights response**: JSON with comprehensive bike sales analysis from multiple agents (fiscal analysis, customer sentiment, summary, and bike lookup).

**Important Notes**:
- **Core Library Workflows** (`classification-agent`, `knowledge-base-agent`, `sql-manipulation-agent`) are available by default and accept simple text prompts
- **Template Workflows** like `bike-insights` require JSON-formatted data with specific fields and are only available after running `ingen init`
- The `bike-insights` workflow is the recommended "Hello World" example for new users
- **Production Security**: Set `INGENIOUS_CHAT_SERVICE__ENABLE_BUILTIN_WORKFLOWS=false` to disable built-in workflows and expose only your custom `ingenious_extensions` workflows

## Next Steps: Creating Custom Workflows

Once you have the basic setup working with the core workflows, you can create your own custom conversation flows:

**[Create Custom Workflows →](docs/guides/custom-workflows.md)**

Learn how to:
- Build custom AI agents for your specific use cases
- Implement multi-agent conversation patterns
- Handle complex business logic and data processing
- Deploy and test your custom workflows

## Documentation

For detailed documentation, see the [docs](https://insight-services-apac.github.io/ingenious/).

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](https://github.com/Insight-Services-APAC/ingenious/blob/main/CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the terms specified in the [LICENSE](https://github.com/Insight-Services-APAC/ingenious/blob/main/LICENSE) file.
