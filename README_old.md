# Insight Ingenious

[![Version](https://img.shields.io/badge/version-0.2.4-blue.svg)](https://github.com/Insight-Services-APAC/ingenious)
[![Python](https://img.shields.io/badge/python-3.13+-green.svg)](https://www.python.org/downloads/)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/Insight-Services-APAC/ingenious)
[![License](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

Ingenious is a tool for quickly setting up APIs to interact with AI Agents. It features multi-agent conversation flows using Microsoft's AutoGen, JWT authentication, and comprehensive Azure service integrations.

## Quick Start

Get up and running in 5 minutes with Azure OpenAI!

### Prerequisites
- Python 3.13 or higher (required - earlier versions are not supported)
- Azure OpenAI API credentials
- [uv package manager](https://docs.astral.sh/uv/)

### AI-Assisted Set Up (give this prompt to your preferred coding agent)

**WARNING: Audit ALL Azure CLI commands!**

```markdown
Follow all steps in [this guide](https://blog.insight-services-apac.dev/ingenious/guides/complete-azure-deployment/).

- Deploy only required resources at minimal cost.
- Use a new resource group: **<your-new-rg-name>**.
- Azure CLI access is available.
```
### 5-Minute Setup

1. **Install and Initialize**:
    ```bash
    # Navigate to your desired project directory first
    cd /path/to/your/project

    # Set up the uv project
    uv init

    # Choose installation based on features needed
    uv add "ingenious[azure-full]" # Recommended: Full Azure integration (core, auth, azure, ai, database, ui)
    # OR
    uv add "ingenious[standard]" # for local testing: includes SQL agent support (core, auth, ai, database)

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
    # Model Configuration (only INGENIOUS_* variables are used by the system)
    INGENIOUS_MODELS__0__MODEL=gpt-4.1-nano
    INGENIOUS_MODELS__0__API_TYPE=rest
    INGENIOUS_MODELS__0__API_VERSION=2024-12-01-preview
    INGENIOUS_MODELS__0__DEPLOYMENT=your-gpt4.1-nano-deployment-name
    INGENIOUS_MODELS__0__API_KEY=your-actual-api-key-here
    INGENIOUS_MODELS__0__BASE_URL=https://your-resource.openai.azure.com/

    # Basic required settings
    INGENIOUS_CHAT_SERVICE__TYPE=multi_agent
    INGENIOUS_CHAT_HISTORY__DATABASE_TYPE=sqlite
    INGENIOUS_CHAT_HISTORY__DATABASE_PATH=./.tmp/chat_history.db
    INGENIOUS_CHAT_HISTORY__MEMORY_PATH=./.tmp

    # Optional: Authentication settings (enabled by default)
    # INGENIOUS_WEB_CONFIGURATION__ENABLE_AUTHENTICATION=false  # To disable auth
    ```

3. **Validate Configuration**:
    ```bash
    uv run ingen validate  # Check configuration before starting
    ```

    **If validation fails with port conflicts**:
    ```bash
    # Check if validation passes with different port
    INGENIOUS_WEB_CONFIGURATION__PORT=8001 uv run ingen validate

    # Or update your .env file before validating:
    echo "INGENIOUS_WEB_CONFIGURATION__PORT=8001" >> .env
    uv run ingen validate
    ```

    > **⚠️ BREAKING CHANGE**: Ingenious now uses **pydantic-settings** for configuration via environment variables. Legacy YAML configuration files (`config.yml`, `profiles.yml`) are **no longer supported** and must be migrated to environment variables with `INGENIOUS_` prefixes. Use the migration script:
    > ```bash
    > uv run python scripts/migrate_config.py --yaml-file config.yml --output .env
    > uv run python scripts/migrate_config.py --yaml-file profiles.yml --output .env.profiles
    > ```

4. **Start the Server**:
    ```bash
    # Start server on port 8000 (recommended for development)
    uv run ingen serve --port 8000

    # Additional options:
    # --host 0.0.0.0         # Bind host (default: 0.0.0.0)
    # --port                 # Port to bind (default: 80 or $WEB_PORT env var)
    # --config config.yml    # Legacy config file (deprecated - use environment variables)
    # --profile production   # Legacy profile (deprecated - use environment variables)
    ```

5. **Verify Health**:
    ```bash
    # Check server health
    curl http://localhost:8000/api/v1/health
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

**Expected Responses**:
- **Successful classification-agent response**: JSON with message analysis and categories
- **Successful knowledge-base-agent response**: JSON with relevant information retrieved (may indicate empty knowledge base initially)
- **Successful sql-manipulation-agent response**: JSON with query results or confirmation

**If you see error responses**, check the troubleshooting section above or the detailed [troubleshooting guide](docs/getting-started/troubleshooting.md).

That's it! You should see a JSON response with AI analysis of the input.

**Next Steps - Test Additional Workflows**:

7. **Test bike-insights Workflow (Requires `ingen init` first)**:

    The `bike-insights` workflow is part of the project template and must be initialized first:
    ```bash
    # First initialize project to get bike-insights workflow
    uv run ingen init

    # Create bike-insights test data file
    # IMPORTANT: bike-insights requires JSON data in the user_prompt field (double-encoded JSON)
    # Method 1: Use printf for precise formatting (recommended)
    printf '%s\n' '{
      "user_prompt": "{\"revision_id\": \"test-v1\", \"identifier\": \"test-001\", \"stores\": [{\"name\": \"Test Store\", \"location\": \"NSW\", \"bike_sales\": [{\"product_code\": \"MB-TREK-2021-XC\", \"quantity_sold\": 2, \"sale_date\": \"2023-04-01\", \"year\": 2023, \"month\": \"April\", \"customer_review\": {\"rating\": 4.5, \"comment\": \"Great bike\"}}], \"bike_stock\": []}]}",
      "conversation_flow": "bike-insights"
    }' > test_bike_insights.json

    # Method 2: Alternative using echo (simpler but watch for shell differences)
    echo '{
      "user_prompt": "{\"revision_id\": \"test-v1\", \"identifier\": \"test-001\", \"stores\": [{\"name\": \"Test Store\", \"location\": \"NSW\", \"bike_sales\": [{\"product_code\": \"MB-TREK-2021-XC\", \"quantity_sold\": 2, \"sale_date\": \"2023-04-01\", \"year\": 2023, \"month\": \"April\", \"customer_review\": {\"rating\": 4.5, \"comment\": \"Great bike\"}}], \"bike_stock\": []}]}",
      "conversation_flow": "bike-insights"
    }' > test_bike_insights.json

    # Method 3: If heredoc is preferred, ensure proper EOF placement
    cat > test_bike_insights.json << 'EOF'
    {
    "user_prompt": "{\"revision_id\": \"test-v1\", \"identifier\": \"test-001\", \"stores\": [{\"name\": \"Test Store\", \"location\": \"NSW\", \"bike_sales\": [{\"product_code\": \"MB-TREK-2021-XC\", \"quantity_sold\": 2, \"sale_date\": \"2023-04-01\", \"year\": 2023, \"month\": \"April\", \"customer_review\": {\"rating\": 4.5, \"comment\": \"Great bike\"}}], \"bike_stock\": []}]}",
    "conversation_flow": "bike-insights"
    }
    EOF

    # Test bike-insights workflow
    curl -X POST http://localhost:8000/api/v1/chat -H "Content-Type: application/json" -d @test_bike_insights.json
    ```

    **Expected bike-insights response**: JSON with comprehensive bike sales analysis from multiple agents (fiscal analysis, customer sentiment, summary, and bike lookup).

**Important Notes**:
- **Core Library Workflows** (`classification-agent`, `knowledge-base-agent`, `sql-manipulation-agent`) are always available and accept simple text prompts
- **Template Workflows** like `bike-insights` require JSON-formatted data with specific fields and are only available after running `ingen init`
- The `bike-insights` workflow is the recommended "Hello World" example for new users

## Workflow Categories

Insight Ingenious provides multiple conversation workflows with different configuration requirements:

### Core Library Workflows (Always Available)
These workflows are built into the Ingenious library and available immediately:

- `classification-agent` - Simple text classification and routing to categories (minimal config required)
- `knowledge-base-agent` - Search and retrieve information from knowledge bases (requires Azure Search or uses local ChromaDB by default)
- `sql-manipulation-agent` - Execute SQL queries based on natural language (requires Azure SQL or uses local SQLite by default)

> **Note**: Core workflows support both hyphenated (`classification-agent`) and underscored (`classification_agent`) naming formats for backward compatibility.

### Template Workflows (Created by `ingen init`)
These workflows are provided as examples in the project template when you run `ingen init`:

- `bike-insights` - Comprehensive bike sales analysis showcasing multi-agent coordination (**ONLY available after `ingen init`** - not included in the core library)

> **Important**: The `bike-insights` workflow is NOT part of the core library. It's a template example that's created when you initialize a new project with `ingen init`. This is the recommended "Hello World" example for learning how to build custom workflows.

## Troubleshooting

For common issues like port conflicts, configuration errors, or workflow problems, see the [detailed troubleshooting guide](docs/getting-started/troubleshooting.md).

## Documentation

For detailed documentation, see the [docs](https://insight-services-apac.github.io/ingenious/).

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](https://github.com/Insight-Services-APAC/ingenious/blob/main/CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the terms specified in the [LICENSE](https://github.com/Insight-Services-APAC/ingenious/blob/main/LICENSE) file.
