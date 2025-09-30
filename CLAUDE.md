# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Context

This is the **ingenious** package - a core AI agent framework library (v0.2.7).

## Communication Style

**CRITICAL**: When working with this codebase:
- **NEVER use emojis** in any communication, code, comments, or documentation
- **Always maintain a concise, professional tone** in all interactions
- Provide direct, clear technical communication without unnecessary elaboration
- Focus on facts and technical accuracy over conversational language

## Package Management

Uses **uv** for Python package and environment management. Python 3.13+ is required.

### Common Commands

```bash
# Install/sync dependencies
uv sync

# Add/remove dependencies
uv add <package>                 # Regular dependency
uv add <package> --dev           # Development dependency
uv remove <package>

# Run commands in environment
uv run pytest                    # Run all tests
uv run pytest tests/unit/test_specific.py  # Run single test file
uv run pytest tests/unit/test_specific.py::TestClass::test_method  # Run specific test

# Type checking and linting
uv run mypy .                    # Type checking (strict mode enabled)
uv run pre-commit run --all-files  # All linting checks

# View dependency tree
uv tree
```

## Building and Testing

```bash
# Run tests with coverage
uv run pytest --cov=ingenious

# Type checking (strict mode enabled)
uv run mypy .

# Linting (uses ruff)
uv run pre-commit run --all-files

# Build package
uv build
```

## High-Level Architecture

### Core Components

- **FastAPI Server** (`ingenious/main/app_factory.py`) - Main API application factory using dependency injection
- **Multi-Agent System** (`ingenious/services/chat_services/multi_agent/`) - AutoGen-based agent orchestration
- **Conversation Flows** (`services/chat_services/multi_agent/conversation_flows/`) - Pluggable workflow patterns
- **Dependency Injection** (`ingenious/services/fastapi_dependencies.py`) - FastAPI-native dependency wiring
- **Configuration** - Pydantic-settings based (`ingenious/config/`) with `INGENIOUS_*` environment variables

### Built-in Conversation Flows

Located in `ingenious/services/chat_services/multi_agent/conversation_flows/`:
- `classification_agent` - Text classification and sentiment analysis
- `knowledge_base_agent` - Knowledge base search with Azure AI Search/ChromaDB
- `sql_manipulation_agent` - Natural language SQL queries

### Key Architectural Patterns

- Repository pattern for data access (`ingenious/db/`)
- Service layer for business logic (`ingenious/services/`)
- Structured logging with correlation IDs (`ingenious/core/structured_logging.py`)
- JWT/Basic auth middleware (`ingenious/auth/`)
- Azure service builders with authentication (`ingenious/client/azure/`)

## CLI Commands

The `ingen` CLI (`ingenious/cli/`) provides:
- `ingen init` - Initialize a new project with templates
- `ingen validate` - Validate configuration
- `ingen serve` - Start API server (default port 80, use --port 8000 to avoid conflicts)
- `ingen run-rest-api-server` - Start with custom host/port
- `ingen test` - Run tests

### Server Startup
```bash
# Recommended for development (avoids port 80 conflicts)
uv run ingen serve --port 8000

# With knowledge base policy for ChromaDB integration
KB_POLICY=local_only uv run ingen serve --port 8000

# For Azure AI Search integration
KB_POLICY=azure uv run ingen serve --port 8000
```

## Configuration

Environment variables with `INGENIOUS_` prefix (using pydantic-settings):

```bash
# Required Azure OpenAI - use Cognitive Services endpoint format (CRITICAL)
INGENIOUS_MODELS__0__API_KEY=your-key
INGENIOUS_MODELS__0__BASE_URL=https://eastus.api.cognitive.microsoft.com/
INGENIOUS_MODELS__0__MODEL=gpt-4o-mini
INGENIOUS_MODELS__0__API_VERSION=2024-12-01-preview
INGENIOUS_MODELS__0__DEPLOYMENT=gpt-4o-mini-deployment
INGENIOUS_MODELS__0__API_TYPE=rest
INGENIOUS_MODELS__0__ROLE=chat

# Model 1: Embedding model (REQUIRED for Azure AI Search)
INGENIOUS_MODELS__1__API_KEY=your-key
INGENIOUS_MODELS__1__BASE_URL=https://eastus.api.cognitive.microsoft.com/
INGENIOUS_MODELS__1__MODEL=text-embedding-3-small
INGENIOUS_MODELS__1__API_VERSION=2024-12-01-preview
INGENIOUS_MODELS__1__DEPLOYMENT=text-embedding-3-small-deployment
INGENIOUS_MODELS__1__API_TYPE=rest
INGENIOUS_MODELS__1__ROLE=embedding

# Chat service
INGENIOUS_CHAT_SERVICE__TYPE=multi_agent
INGENIOUS_CHAT_HISTORY__DATABASE_TYPE=sqlite  # or azuresql or cosmos
INGENIOUS_CHAT_HISTORY__DATABASE_PATH=./.tmp/chat_history.db

# Web server (use port 8000 to avoid conflicts)
INGENIOUS_WEB_CONFIGURATION__PORT=8000
INGENIOUS_WEB_CONFIGURATION__IP_ADDRESS=0.0.0.0

# Authentication (optional)
INGENIOUS_WEB_CONFIGURATION__AUTHENTICATION__ENABLE=true
INGENIOUS_WEB_CONFIGURATION__AUTHENTICATION__USERNAME=admin
INGENIOUS_WEB_CONFIGURATION__AUTHENTICATION__PASSWORD=secure_password

# Knowledge base configuration (CRITICAL for knowledge-base-agent)
KB_POLICY=local_only  # or azure_only, prefer_azure, prefer_local
KB_TOPK_DIRECT=3
KB_TOPK_ASSIST=5
KB_MODE=direct

# Local SQL database for sql-manipulation workflows
INGENIOUS_LOCAL_SQL_DB__DATABASE_PATH=./.tmp/sample_sql.db
```

**CRITICAL Configuration Notes**:
- **Azure OpenAI Endpoint**: Must use Cognitive Services format (`https://eastus.api.cognitive.microsoft.com/`) not deprecated OpenAI format (`https://your-resource.openai.azure.com/`)
- **Dual Model Setup**: Azure AI Search requires TWO separate models with different ROLE values (chat + embedding)
- **KB_POLICY**: Essential for knowledge-base-agent functionality. Use `KB_POLICY=local_only` for development
- **Port Conflicts**: Always use port 8000 to avoid conflicts with system port 80

Configuration now relies on environment variables (`INGENIOUS_*`). Ensure `.env` is populated instead of using legacy YAML files.

## Development Workflow

### Adding New Conversation Flows

1. Create flow module in `ingenious_extensions/services/chat_services/multi_agent/conversation_flows/your_flow/`
2. Implement `IConversationFlow` interface with `get_conversation_response` method
3. Define agents inline or import from `ingenious/models/ag_agents/`
4. Create Jinja2 prompt templates in `templates/prompts/`
5. **CRITICAL**: Set `export PYTHONPATH=$(pwd):$PYTHONPATH` before server startup for workflow discovery
6. Restart server after adding new workflows for discovery
7. Flow is auto-discovered by name match with `conversation_flow` parameter

### Important Workflow Development Notes
- **Revision ID**: Use `"revision_id": "quickstart-1"` in examples (not `"test-v1"`) to match actual template structure
- **Template Location**: Templates created by `ingen init` are stored under `quickstart-1/` directory
- **Authentication**: Both Basic Auth and JWT work seamlessly with custom workflows
- **Error Handling**: Always implement proper exception handling in conversation flows

### Project Template

Running `ingen init` creates:
- `ingenious_extensions/` directory with example `bike-insights` workflow
- Templates directory with Jinja2 prompts
- Sample configuration files

### Testing

```bash
# Unit tests only
uv run pytest tests/unit/

# Integration tests (requires Azure credentials)
uv run pytest tests/integration/

# Specific test markers
uv run pytest -m "not azure_integration"  # Skip Azure tests
uv run pytest -m unit  # Unit tests only
uv run pytest -m slow  # Slow-running tests
uv run pytest -m e2e   # End-to-end tests (requires external APIs)
uv run pytest -m docs  # Document parsing tests

# With verbose output
uv run pytest -v

# Coverage report
uv run pytest --cov=ingenious --cov-report=html
```

## Database Integration

Supports multiple backends via repository pattern:
- **SQLite** (default) - Local development
- **Azure SQL** - Production deployment via pyodbc
- **Cosmos DB** - Document storage
- **ChromaDB** - Vector database for embeddings
- Connection pooling via `ingenious/db/connection_pool.py`

## Azure Service Integration

### Azure Search (`ingenious/services/azure_search/`)
- Classic retrieval with BM25
- Document fusion (DAT)
- Semantic reranking
- Generative answering (RAG)
- CLI tool: `uv run azure-search "query"`

### Azure Blob Storage (`ingenious/files/azure/`)
- Prompt template storage
- Document upload/download
- File summarization support

### Azure Authentication (`ingenious/client/azure/`)
- Service principal support
- Managed identity
- Interactive browser auth
- Connection string auth

## Type Safety

Strict mypy configuration with:
- `strict = true` for core library
- Relaxed rules for tests and certain legacy modules (multi_agent, auth, files, etc.)
- Run `uv run mypy .` before submitting changes

### Complete Quality Assurance Workflow
```bash
# CRITICAL: Run this sequence before any commits or PRs
uv run ingen validate              # Configuration validation (must pass first)
uv run pytest -m "not slow"       # Fast tests only (919 tests should pass)
uv run pre-commit run --all-files  # Linting and formatting (all hooks must pass)
uv run mypy . --exclude test_dir   # Type checking (324 files, no issues)

# For comprehensive validation:
uv run pytest --cov=ingenious     # Full test suite with coverage
```

### Authentication Testing Patterns
```bash
# Test without authentication (should get 401 for protected endpoints)
curl -X POST http://localhost:8000/api/v1/chat -H "Content-Type: application/json" -d @test.json

# Test with Basic Auth
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic $(echo -n 'username:password' | base64)" \
  -d @test.json

# Test with JWT (get token first)
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "secure_password"}' | \
  python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d @test.json
```

### Prompt Template Management

Templates are managed via API endpoints:
```bash
# List templates for a revision
curl -X GET "http://localhost:8000/api/v1/prompts/list/quickstart-1" -H "Authorization: Bearer $TOKEN"

# View specific template
curl -X GET "http://localhost:8000/api/v1/prompts/view/quickstart-1/summary_prompt.jinja" -H "Authorization: Bearer $TOKEN"

# Update/create template
curl -X POST "http://localhost:8000/api/v1/prompts/update/quickstart-1/my_template.jinja" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "Your Jinja2 template content here"}'
```

**Storage Location**:
- **Local**: `templates/prompts/quickstart-1/`
- **Azure Blob**: `templates/prompts/quickstart-1/` (same structure)
- Templates are loaded dynamically based on `revision_id` in requests

## Package Features

Install groups (via `uv add "ingenious[group]"`):
- `minimal` - Basic API functionality only
- `core` - Common production functionality
- `auth` - Authentication and security
- `azure` - Azure cloud integrations
- `ai` - AI and agent functionality
- `database` - Database connectivity
- `ui` - Web UI with Flask
- `standard` - Core + auth + AI + database
- `azure-full` - Full Azure integration (recommended)
- `full` - All features including document processing and ML
