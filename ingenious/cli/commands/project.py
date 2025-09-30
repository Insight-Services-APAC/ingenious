"""
Project management CLI commands for Insight Ingenious.

This module contains commands for initializing projects and managing project structure.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ingenious.cli.base import BaseCommand, CommandError, ExitCode
from ingenious.cli.utilities import FileOperations, OutputFormatters


class InitCommand(BaseCommand):
    """Initialize a new Insight Ingenious project."""

    def execute(self, **kwargs: Any) -> None:
        """
        Initialize a new Insight Ingenious project in the current directory.

        Creates a complete project structure with:
        • .env.example - Example environment variables for pydantic-settings configuration
        • ingenious_extensions/ - Your custom agents and workflows
        • templates/prompts/quickstart-1/ - Ready-to-use bike-insights workflow templates
        • Dockerfile - Docker containerization setup
        • .dockerignore - Docker build exclusions
        • tmp/ - Temporary files and memory storage

        🎯 INCLUDES: Pre-configured quickstart-1 templates for immediate bike-insights testing!
        """
        self.start_progress("Initializing project structure...")

        try:
            self._create_project_structure()
            self.stop_progress()

            self.print_success("Project initialization completed!")
            self._show_next_steps()

        except Exception as e:
            self.stop_progress()
            raise CommandError(
                f"Project initialization failed: {e}", ExitCode.GENERAL_ERROR
            )

    def _create_project_structure(self) -> None:
        """Create the project directory structure."""
        base_path = Path(__file__).parent.parent.parent
        templates_paths = {
            "ingenious_extensions": base_path / "ingenious_extensions_template",
            "tmp": None,  # No template, just create the folder
        }

        # Create directories from templates
        for folder_name, template_path in templates_paths.items():
            destination = Path.cwd() / folder_name

            # Skip if the destination folder already exists
            if destination.exists():
                self.print_warning(
                    f"Folder '{folder_name}' already exists. Skipping..."
                )
                continue

            # Check if a template path exists (if applicable)
            if template_path and not template_path.exists():
                self.print_warning(
                    f"Template directory '{template_path}' not found. Skipping..."
                )
                continue

            try:
                if template_path:
                    # Copy from template
                    if not FileOperations.copy_tree_safe(template_path, destination):
                        raise OSError(f"Failed to copy template for {folder_name}")
                    self.print_success(f"Created '{folder_name}/' from template")
                else:
                    # Just create the directory
                    FileOperations.ensure_directory(destination, folder_name)
                    self.print_success(f"Created '{folder_name}/' directory")

            except Exception as e:
                raise CommandError(
                    f"Failed to create {folder_name}: {e}", ExitCode.GENERAL_ERROR
                )

        # Create environment configuration files
        self._create_env_files(base_path)

        # Create Docker files
        self._create_docker_files(base_path)

        # Create standalone templates directory
        self._create_templates_directory(base_path)

    def _create_env_files(self, base_path: Path) -> None:
        """Create environment configuration files in the project root."""
        env_files = {
            ".env.example": base_path / "config_templates" / ".env.example",
        }

        for filename, template_path in env_files.items():
            destination = Path.cwd() / filename

            if destination.exists():
                self.print_warning(f"File '{filename}' already exists. Skipping...")
                continue

            try:
                if template_path.exists():
                    shutil.copy2(template_path, destination)
                    self.print_success(f"Created '{filename}' from template")
                else:
                    # Create a default file if template doesn't exist
                    self._create_default_env_file(filename, destination)
                    self.print_success(f"Created default '{filename}'")

            except Exception as e:
                self.logger.error(f"Failed to create {filename}: {e}")
                # Don't fail the entire operation for config files

    def _create_docker_files(self, base_path: Path) -> None:
        """Create Docker-related files."""
        docker_files = {
            "Dockerfile": base_path / "docker_templates" / "Dockerfile",
            ".dockerignore": base_path / "docker_templates" / ".dockerignore",
        }

        for filename, template_path in docker_files.items():
            destination = Path.cwd() / filename

            if destination.exists():
                self.print_warning(f"File '{filename}' already exists. Skipping...")
                continue

            try:
                if template_path.exists():
                    shutil.copy2(template_path, destination)
                    self.print_success(f"Created '{filename}' from template")
                else:
                    # Create a basic file if template doesn't exist
                    self._create_default_docker_file(filename, destination)
                    self.print_success(f"Created default '{filename}'")

            except Exception as e:
                self.logger.error(f"Failed to create {filename}: {e}")
                # Don't fail the entire operation for Docker files

    def _create_default_env_file(self, filename: str, destination: Path) -> None:
        """Create a default environment configuration file if template is missing."""
        if filename == ".env.example":
            content = """# Insight Ingenious Configuration
# Environment variables for pydantic-settings configuration
# Copy this file to .env and update with your actual values

# Core AI Model Configuration (REQUIRED)
# API key for your OpenAI or Azure OpenAI service
INGENIOUS_MODELS__0__API_KEY=your-api-key-here
# Base URL for Azure OpenAI (use Cognitive Services endpoint format)
INGENIOUS_MODELS__0__BASE_URL=https://eastus.api.cognitive.microsoft.com/
# Model name (e.g., gpt-4o-mini, gpt-4, gpt-3.5-turbo)
INGENIOUS_MODELS__0__MODEL=gpt-4o-mini
# Azure OpenAI API version
INGENIOUS_MODELS__0__API_VERSION=2024-12-01-preview
# Azure OpenAI deployment name (usually same as model)
INGENIOUS_MODELS__0__DEPLOYMENT=gpt-4o-mini
# API type for Azure OpenAI
INGENIOUS_MODELS__0__API_TYPE=rest
# Role for this model (chat for generation, embedding for vector operations)
INGENIOUS_MODELS__0__ROLE=chat

# Model 1: Embedding model (REQUIRED for Azure AI Search)
INGENIOUS_MODELS__1__API_KEY=your-api-key-here
INGENIOUS_MODELS__1__BASE_URL=https://eastus.api.cognitive.microsoft.com/
INGENIOUS_MODELS__1__MODEL=text-embedding-3-small
INGENIOUS_MODELS__1__API_VERSION=2024-12-01-preview
INGENIOUS_MODELS__1__DEPLOYMENT=text-embedding-3-small-deployment
INGENIOUS_MODELS__1__API_TYPE=rest
INGENIOUS_MODELS__1__ROLE=embedding

# Web Server Configuration (OPTIONAL)
# Port for the web server (use 8000 to avoid conflicts)
INGENIOUS_WEB_CONFIGURATION__PORT=8000
# IP address to bind (default: 0.0.0.0)
INGENIOUS_WEB_CONFIGURATION__IP_ADDRESS=0.0.0.0
# Enable authentication (default: false)
INGENIOUS_WEB_CONFIGURATION__AUTHENTICATION__ENABLE=false

# Chat History Database (OPTIONAL)
# Database type: sqlite (local) or azuresql (cloud)
INGENIOUS_CHAT_HISTORY__DATABASE_TYPE=sqlite
# Path for local SQLite database
INGENIOUS_CHAT_HISTORY__DATABASE_PATH=./.tmp/chat_history.db
# Memory storage path
INGENIOUS_CHAT_HISTORY__MEMORY_PATH=./.tmp

# Chat Service Configuration (REQUIRED)
# Chat service type for multi-agent workflows
INGENIOUS_CHAT_SERVICE__TYPE=multi_agent

# Logging Configuration (OPTIONAL)
# Log levels: debug, info, warning, error
INGENIOUS_LOGGING__ROOT_LOG_LEVEL=info
INGENIOUS_LOGGING__LOG_LEVEL=info

# Optional: Azure SQL Database (for Azure SQL workflows)
# Change INGENIOUS_CHAT_HISTORY__DATABASE_TYPE to 'azuresql' to enable Azure SQL
# INGENIOUS_AZURE_SQL_SERVICES__DATABASE_CONNECTION_STRING=Driver={ODBC Driver 18 for SQL Server};Server=tcp:YOUR_SERVER.database.windows.net,1433;Database=YOUR_DATABASE;Uid=YOUR_USERNAME;Pwd=YOUR_PASSWORD;Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;
# INGENIOUS_AZURE_SQL_SERVICES__DATABASE_NAME=your_database_name
# INGENIOUS_AZURE_SQL_SERVICES__TABLE_NAME=chat_history

# Optional: Cosmos DB Configuration (if using Cosmos DB instead of SQL)
# INGENIOUS_COSMOS_SERVICE__URI=https://your-cosmos-account.documents.azure.com:443/
# INGENIOUS_COSMOS_SERVICE__DATABASE_NAME=your-database-name
# INGENIOUS_COSMOS_SERVICE__AUTHENTICATION_METHOD=token
# INGENIOUS_COSMOS_SERVICE__API_KEY=your-cosmos-primary-key

# Knowledge base configuration - local ChromaDB for development
KB_POLICY=local_only
KB_TOPK_DIRECT=3
KB_TOPK_ASSIST=5
KB_MODE=direct

# Optional: Azure Search (for knowledge-base workflows in production)
# INGENIOUS_AZURE_SEARCH_SERVICES__0__KEY=your-search-api-key
# INGENIOUS_AZURE_SEARCH_SERVICES__0__ENDPOINT=https://your-search-service.search.windows.net

# Local SQL database configuration - local SQLite for development
INGENIOUS_LOCAL_SQL_DB__DATABASE_PATH=./.tmp/sample_sql.db

# Optional: Scrapfly API for dataprep commands
# SCRAPFLY_API_KEY=your-scrapfly-api-key

# Optional: Azure Blob Storage (for cloud-based file storage)
# Change INGENIOUS_FILE_STORAGE__REVISIONS__STORAGE_TYPE to 'azure' to enable
# INGENIOUS_FILE_STORAGE__REVISIONS__ENABLE=true
# INGENIOUS_FILE_STORAGE__REVISIONS__STORAGE_TYPE=azure
# INGENIOUS_FILE_STORAGE__REVISIONS__CONTAINER_NAME=prompts
# INGENIOUS_FILE_STORAGE__REVISIONS__PATH=./
# INGENIOUS_FILE_STORAGE__REVISIONS__URL=https://YOUR_STORAGE_ACCOUNT.blob.core.windows.net
# INGENIOUS_FILE_STORAGE__REVISIONS__TOKEN=DefaultEndpointsProtocol=https;AccountName=YOUR_ACCOUNT;AccountKey=YOUR_KEY;EndpointSuffix=core.windows.net

"""
        else:
            content = f"# {filename} - Created by Insight Ingenious\n"

        with open(destination, "w") as f:
            f.write(content)

    def _create_default_docker_file(self, filename: str, destination: Path) -> None:
        """Create a default Docker file if template is missing."""
        if filename == "Dockerfile":
            content = """FROM python:3.13-slim

WORKDIR /app

# Install system dependencies including ODBC driver for Azure SQL
RUN apt-get update && apt-get install -y \\
    git \\
    curl \\
    gnupg2 \\
    unixodbc-dev \\
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /usr/share/keyrings/microsoft-archive-keyring.gpg \\
    && echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-archive-keyring.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \\
    && apt-get update \\
    && ACCEPT_EULA=Y apt-get install -y msodbcsql18 \\
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Copy project files
COPY pyproject.toml .

# Install dependencies with uv
RUN uv sync

# Copy application code
COPY . .

# Expose port
EXPOSE 80

# Set environment variable to use port 80 for production
ENV INGENIOUS_WEB_CONFIGURATION__PORT=80

# Run the application
CMD ["uv", "run", "python", "-m", "ingenious.cli", "serve"]
"""
        elif filename == ".dockerignore":
            content = """.git
.gitignore
.env
.env.*
__pycache__
*.pyc
*.pyo
*.pyd
.Python
env
pip-log.txt
pip-delete-this-directory.txt
.tox
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*.cover
*.log
.venv
.pytest_cache
.mypy_cache
functional_test_outputs/
tmp/
.tmp/
"""
        else:
            content = f"# {filename} - Created by Insight Ingenious\n"

        with open(destination, "w") as f:
            f.write(content)

    def _create_templates_directory(self, base_path: Path) -> None:
        """Create standalone templates/prompts/quickstart-1/ directory with bike-insights templates."""
        templates_dir = Path.cwd() / "templates" / "prompts" / "quickstart-1"

        if templates_dir.exists():
            self.print_warning("Templates directory already exists. Skipping...")
            return

        try:
            # Create the directory structure
            templates_dir.mkdir(parents=True, exist_ok=True)

            # Copy prompt template files from ingenious_extensions_template
            source_templates = (
                base_path / "ingenious_extensions_template" / "templates" / "prompts"
            )

            if source_templates.exists():
                for template_file in source_templates.glob("*.jinja"):
                    destination_file = templates_dir / template_file.name
                    shutil.copy2(template_file, destination_file)

                self.print_success(
                    f"Created 'templates/prompts/quickstart-1/' with {len(list(source_templates.glob('*.jinja')))} template files"
                )
            else:
                # Create the directory but warn about missing templates
                self.print_warning(
                    "Source templates not found, created empty templates directory"
                )

        except Exception as e:
            self.logger.error(f"Failed to create templates directory: {e}")
            # Don't fail the entire operation for templates

    def _show_next_steps(self) -> None:
        """Show next steps after project initialization."""
        next_steps = [
            "1. Copy .env.example to .env and add your credentials:",
            "   cp .env.example .env",
            "2. Edit .env file with your API keys and configuration",
            "3. Validate your configuration:",
            "   ingen validate",
            "4. Start the server:",
            "   ingen serve",
            "5. Test the sample bike-insights workflow:",
            "   curl -X POST http://localhost:80/api/v1/chat \\",
            "     -H 'Content-Type: application/json' \\",
            '     -d \'{"user_prompt": "Analyze bike sales", "conversation_flow": "bike-insights"}\'',
            "",
            "🐳 Docker Deployment:",
            "6. Build production container:",
            "   docker build -t ingenious-app .",
            "7. Run with environment:",
            "   docker run --env-file .env -p 8080:80 ingenious-app",
        ]

        panel = OutputFormatters.create_info_panel(
            "\n".join(next_steps), "🚀 Next Steps", "green"
        )
        self.console.print(panel)

        self.console.print(
            "\n[bold yellow]💡 For detailed configuration help:[/bold yellow]"
        )
        self.console.print("   ingen workflows --help")


# Backward compatibility functions
def register_commands(app: Any, console: Any) -> None:
    """Register project-related commands with the typer app."""

    @app.command(name="init", help="Initialize a new Insight Ingenious project")  # type: ignore[misc]
    def init() -> None:
        """
        🏗️  Initialize a new Insight Ingenious project in the current directory.

        Creates a complete project structure with:
        • .env.example - Example environment variables for pydantic-settings configuration
        • ingenious_extensions/ - Your custom agents and workflows
        • templates/prompts/quickstart-1/ - Ready-to-use bike-insights workflow templates
        • Dockerfile - Docker containerization setup
        • .dockerignore - Docker build exclusions
        • tmp/ - Temporary files and memory storage

        🎯 INCLUDES: Pre-configured quickstart-1 templates for immediate bike-insights testing!

        NEXT STEPS after running this command:
        1. Copy .env.example to .env and add your credentials
        2. Edit .env file with your API keys and configuration
        3. Validate your configuration: ingen validate
        4. Start the server: ingen serve

        For detailed configuration help: ingen workflows --help
        """
        cmd = InitCommand(console)
        cmd.run()

    # Keep old command for backward compatibility
    @app.command(hidden=True)  # type: ignore[misc]
    def initialize_new_project() -> None:
        """Legacy command that delegates to the new init command."""
        cmd = InitCommand(console)
        cmd.run()
