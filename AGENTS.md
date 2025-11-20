# AGENTS.md

This file provides guidance to coding agents when working with code in this repository.

# Important Note on Your Context Window
Your context window will be automatically compacted as it approaches its limit, allowing you to continue working indefinitely from where you left off. Therefore, do not stop tasks early due to token budget concerns. As you approach your token budget limit, save your current progress and state to memory before the context window refreshes. Always be as persistent and autonomous as possible and complete tasks fully, even if the end of your budget is approaching. Never artificially stop any task early regardless of the context remaining.

## Repository Context

This is the **ingenious** package - a core AI agent framework library (v0.2.7).

## Communication Style

**CRITICAL**: When working with this codebase:
- **NEVER use emojis** in any communication, code, comments, or documentation
- **Always maintain a concise, professional tone** in all interactions
- Provide direct, clear technical communication without unnecessary elaboration
- Focus on facts and technical accuracy over conversational language

## Testing and Development Files

**CRITICAL**: All testing artifacts, temporary files, and development scripts must be placed in the `/tmp` folder to maintain repository cleanliness:

- Development scripts and experiments
- Temporary output files
- Test artifacts and logs
- Mock data generators

This prevents clutter in the working directory and ensures consistent cleanup across development environments.

## Package Management

Uses **uv** for Python package and environment management. Python 3.13+ is required.

## High-Level Architecture

### Core Components

- **FastAPI Server** (`ingenious/main/app_factory.py`) - Main API application factory using dependency injection
- **Multi-Agent System** (`ingenious/services/chat_services/multi_agent/`) - AutoGen-based agent orchestration
- **Conversation Flows** (`services/chat_services/multi_agent/conversation_flows/`) - Pluggable workflow patterns
- **Dependency Injection** (`ingenious/services/fastapi_dependencies.py`) - FastAPI-native dependency wiring
- **Configuration** - Pydantic-settings based (`ingenious/config/`) with `INGENIOUS_*` environment variables

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
INGENIOUS_MODELS__0__MODEL=gpt-5-mini
INGENIOUS_MODELS__0__API_VERSION=2024-12-01-preview
INGENIOUS_MODELS__0__DEPLOYMENT=gpt-5-mini-deployment
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
