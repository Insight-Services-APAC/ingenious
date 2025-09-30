"""
Server-related CLI commands for Insight Ingenious.

This module contains commands for starting and managing the API server.
"""

from __future__ import annotations

import importlib
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from ingenious.config.main_settings import IngeniousSettings
import pkgutil
from pathlib import Path
from sysconfig import get_paths
from typing import Optional

import typer
import uvicorn
from dotenv import load_dotenv
from rich.console import Console
from typing_extensions import Annotated

from ingenious.cli.utilities import CliFunctions
from ingenious.config import get_config
from ingenious.core.structured_logging import get_logger

# Load environment variables from .env file
load_dotenv()

# Initialize logger
logger = get_logger(__name__)


def make_app(config: "IngeniousSettings") -> "FastAPI":
    # keep the import late so your env var ordering still works

    from ingenious.main import create_app

    return create_app(config)


def register_commands(app: typer.Typer, console: Console) -> None:
    """Register server-related commands with the typer app."""

    @app.command(name="serve", help="Start the API server with web interface")
    def serve(
        env_file: Annotated[
            Optional[str],
            typer.Option(
                "--env-file",
                "-e",
                help="Path to a .env file (default: auto-discover .env in working directory)",
            ),
        ] = None,
        host: Annotated[
            str,
            typer.Option(
                "--host", "-h", help="Host to bind the server (default: 0.0.0.0)"
            ),
        ] = "127.0.0.1",
        port: Annotated[
            int,
            typer.Option(
                "--port", help="Port to bind the server (default: 80 or $WEB_PORT)"
            ),
        ] = int(os.getenv("WEB_PORT", "80")),
        no_prompt_tuner: Annotated[
            bool,
            typer.Option(
                "--no-prompt-tuner", help="Disable the prompt tuner interface"
            ),
        ] = False,
    ) -> None:
        """
        🚀 Start the Insight Ingenious API server with web interface.

        The server provides:
        • REST API endpoints for agent workflows
        • Prompt tuning interface at /prompt-tuner (unless disabled)

        AVAILABLE WORKFLOWS & CONFIGURATION REQUIREMENTS:

        ✅ Minimal Configuration (Azure OpenAI only):
          • classification-agent - Route input to specialized agents
          • bike-insights - Sample domain-specific workflow

        🔍 Requires Azure Search Services:
          • knowledge-base-agent - Search knowledge bases

        📊 Requires Database Configuration:
          • sql-manipulation-agent - Execute SQL queries

        📄 Optional Azure Document Intelligence:
          • document-processing - Extract text from PDFs/images

        QUICK TEST:
          curl -X POST http://localhost:{port}/api/v1/chat \\
            -H "Content-Type: application/json" \\
            -d '{{"user_prompt": "Hello", "conversation_flow": "classification-agent"}}'

        For detailed configuration: ingen workflows --help
        """
        return run_rest_api_server(
            env_file=env_file,
            host=host,
            port=port,
        )

    # Keep old command for backward compatibility
    @app.command(hidden=True)
    def run_rest_api_server(
        env_file: Annotated[
            Optional[str],
            typer.Argument(
                help="Optional path to a .env file. Uses default dotenv discovery when omitted."
            ),
        ] = None,
        host: Annotated[
            str,
            typer.Argument(
                help="The host to run the server on. Default is 127.0.0.1. For docker or external access use 0.0.0.0"
            ),
        ] = "127.0.0.1",
        port: Annotated[
            int,
            typer.Argument(help="The port to run the server on. Default is 80."),
        ] = 80,
    ) -> None:
        """
        Run a FastAPI server that presents your agent workflows via REST endpoints.

        AVAILABLE WORKFLOWS & CONFIGURATION REQUIREMENTS:

        ⭐ "Hello World" Workflow (Azure OpenAI only):
          • bike-insights - **RECOMMENDED STARTING POINT** - Multi-agent bike sales analysis

        ✅ Simple Text Processing (Azure OpenAI only):
          • classification_agent - Route input to specialized agents

        🔍 Requires Azure Search Services:
          • knowledge_base_agent - Search knowledge bases

        📊 Requires Database Configuration:
          • sql_manipulation_agent - Execute SQL queries

        📄 Optional Azure Document Intelligence:
          • document-processing - Extract text from PDFs/images

        For detailed configuration requirements, see:
        docs/workflows/README.md

        QUICK TEST (Hello World):
        curl -X POST http://localhost:PORT/api/v1/chat \\
          -H "Content-Type: application/json" \\
          -d '{
            "user_prompt": "{\\"stores\\": [{\\"name\\": \\"Hello Store\\", \\"location\\": \\"NSW\\", \\"bike_sales\\": [{\\"product_code\\": \\"HELLO-001\\", \\"quantity_sold\\": 1, \\"sale_date\\": \\"2023-04-01\\", \\"year\\": 2023, \\"month\\": \\"April\\", \\"customer_review\\": {\\"rating\\": 5.0, \\"comment\\": \\"Great first experience!\\"}}], \\"bike_stock\\": []}], \\"revision_id\\": \\"hello-1\\", \\"identifier\\": \\"world\\"}",
            "conversation_flow": "bike-insights"
          }'
        """
        if env_file:
            env_path = Path(env_file).expanduser().resolve()
            if env_path.exists():
                load_dotenv(env_path, override=True)
                logger.info(
                    "Loaded environment file",
                    env_file=str(env_path),
                    operation="environment_setup",
                )
            else:
                logger.warning(
                    "Specified .env file not found, continuing with default environment",
                    env_file=str(env_path),
                    operation="environment_setup",
                )
        else:
            load_dotenv(override=True)
            logger.debug(
                "Loaded environment variables using default .env discovery",
                operation="environment_setup",
            )

        config = get_config()

        # Override host and port from CLI parameters only if they differ from defaults
        config.web_configuration.ip_address = host

        # Only override port if it was explicitly provided via CLI (different from env var default)
        default_port_from_env = int(os.getenv("WEB_PORT", "80"))
        if port != default_port_from_env or os.getenv("WEB_PORT") is not None:
            # If port was explicitly set via CLI or WEB_PORT env var, use it
            config.web_configuration.port = port
        # Otherwise, let the configuration system use INGENIOUS_WEB_CONFIGURATION__PORT

        # We need to clean this up and probably separate overall system config from fast api, eg. set the config here in cli and then pass it to FastAgentAPI
        # As soon as we import FastAgentAPI, config will be loaded hence to ensure that the environment variables above are loaded first we need to import FastAgentAPI after setting the environment variables

        os.environ["LOADENV"] = "False"
        if env_file:
            console.print(
                f"Running Ingenious using environment file {env_file}",
                style="info",
            )
        else:
            console.print(
                "Running Ingenious using environment variables (dotenv auto-discovery)",
                style="info",
            )
        # If the code has been pip installed then recursively copy the ingenious folder into the site-packages directory
        if CliFunctions.PureLibIncludeDirExists():
            src = Path(os.getcwd()) / Path("ingenious/")
            if os.path.exists(src):
                CliFunctions.copy_ingenious_folder(
                    src, Path(get_paths()["purelib"]) / Path("ingenious/")
                )

        logger.info(
            "Working directory set",
            working_directory=os.getcwd(),
            operation="environment_setup",
        )

        def log_namespace_modules(namespace: str) -> None:
            try:
                package = importlib.import_module(namespace)
                if hasattr(package, "__path__"):
                    modules = [
                        module_info.name
                        for module_info in pkgutil.iter_modules(package.__path__)
                    ]
                    logger.debug(
                        "Namespace modules discovered",
                        namespace=namespace,
                        modules=modules,
                        module_count=len(modules),
                    )
                else:
                    logger.debug("Namespace is not a package", namespace=namespace)
            except ImportError as e:
                logger.warning(
                    "Failed to import namespace", namespace=namespace, error=str(e)
                )

        os.environ["INGENIOUS_WORKING_DIR"] = str(Path(os.getcwd()))
        os.chdir(str(Path(os.getcwd())))
        log_namespace_modules(
            "ingenious.services.chat_services.multi_agent.conversation_flows"
        )

        app = make_app(config)
        uvicorn.run(
            app,
            host=config.web_configuration.ip_address,
            port=config.web_configuration.port,
        )

    @app.command(name="prompt-tuner", help="Start standalone prompt tuning interface")
    def prompt_tuner(
        port: Annotated[
            int,
            typer.Option(
                "--port", "-p", help="Port for the prompt tuner (default: 5000)"
            ),
        ] = 5000,
        host: Annotated[
            str,
            typer.Option(
                "--host",
                "-h",
                help="Host to bind the prompt tuner (default: 127.0.0.1)",
            ),
        ] = "127.0.0.1",
    ) -> None:
        """
        🎯 Start the standalone prompt tuning web interface.

        The prompt tuner allows you to:
        • Edit and test agent prompts
        • Run batch tests with sample data
        • Compare different prompt versions
        • Download test results

        Access the interface at: http://{host}:{port}

        Note: This starts only the prompt tuner, not the full API server.
        For the complete server with all interfaces, use: ingen serve
        """
        logger.info(
            "Starting prompt tuner server",
            host=host,
            port=port,
            url=f"http://{host}:{port}",
            operation="prompt_tuner_startup",
        )
        console.print(f"🎯 Starting prompt tuner at http://{host}:{port}")
        console.print(
            "💡 Tip: Use 'ingen serve' to start the full server with all interfaces"
        )

        console.print("[red]❌ Prompt tuner has been removed from this version[/red]")
        console.print("Use the main API server instead: ingen serve")
        raise typer.Exit(1)
