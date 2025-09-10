"""
Server-related CLI commands for Insight Ingenious.

This module defines the Typer CLI commands that start and manage the API server.
It also centralizes host/port resolution so tests and deployments get consistent
behavior. In particular, when a deploy-style port is configured via `WEB_PORT`
or `PORT`, the server should bind to `0.0.0.0` unless an explicit `--host`
override is provided. CLI flags always take precedence over environment values.

Usage:
    - `ingen serve` starts the main API server.
    - `ingen run-rest-api-server` is a hidden/legacy alias used by tests.
Key entry points:
    - `register_commands()`
    - `resolve_host_port()`
"""

from __future__ import annotations

import importlib
import os
import pkgutil
from pathlib import Path
from sysconfig import get_paths
from typing import TYPE_CHECKING, Optional, Tuple

import typer
import uvicorn
from dotenv import load_dotenv
from rich.console import Console
from typing_extensions import Annotated

from ingenious.cli.utilities import CliFunctions
from ingenious.config import get_config
from ingenious.core.structured_logging import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI
    from ingenious.config.main_settings import IngeniousSettings

# Load environment variables from .env file
load_dotenv()

# Initialize logger
logger = get_logger(__name__)

# -----------------------
# Module-level constants
# -----------------------
DEFAULT_LOCAL_HOST = "127.0.0.1"
BIND_ALL_HOST = "0.0.0.0"
DEFAULT_PORT = 80
DEFAULT_TUNER_PORT = 5000


def resolve_host_port(host_flag: Optional[str], port_flag: Optional[int]) -> Tuple[str, int]:
    """Resolve (host, port) honoring env precedence and CLI overrides.

    What:
        - If WEB_PORT or PORT is set and the host was not explicitly overridden,
          bind to 0.0.0.0 (container/PaaS semantics).
        - CLI flags, when provided, always win over env/defaults.

    Why:
        Tests expect binding to all interfaces when a deploy-style port is
        provided via environment (WEB_PORT/PORT). Reading env here (call time)
        ensures monkeypatched env in tests is respected.

    Args:
        host_flag: Host from CLI (or None).
        port_flag: Port from CLI (or None).

    Returns:
        A (host, port) pair ready for `uvicorn.run(...)`.
    """
    env_web = os.getenv("WEB_PORT")
    env_proc = os.getenv("PORT")

    env_port: Optional[int] = None
    for candidate in (env_web, env_proc):
        if candidate is None:
            continue
        try:
            env_port = int(candidate)
            break
        except ValueError:
            # Ignore non-integer env values
            continue

    # Port: CLI > ENV > DEFAULT
    port = port_flag if port_flag is not None else (env_port or DEFAULT_PORT)

    # Host:
    # - If CLI host is provided, use it as-is.
    # - Else, if an env port is present (regardless of the CLI port value),
    #   bind to 0.0.0.0. Otherwise, default to loopback.
    if host_flag is not None:
        host = host_flag
    else:
        host = BIND_ALL_HOST if env_port is not None else DEFAULT_LOCAL_HOST

    return host, port


def make_app(config: "IngeniousSettings") -> "FastAPI":
    """Create and return the FastAPI application for the given configuration.

    Why:
        This import is intentionally late so environment variables (set by the
        CLI prior to calling this function) are honored by the app factory.
    """
    from ingenious.main import create_app

    return create_app(config)


def register_commands(app: typer.Typer, console: Console) -> None:
    """Register server-related commands with the typer app.

    Args:
        app: The Typer application to register the commands on.
        console: Rich console used for user-facing messages.
    """

    @app.command(name="serve", help="Start the API server with web interface")
    def serve(
        config: Annotated[
            Optional[str],
            typer.Option(
                "--config",
                "-c",
                help=(
                    "Path to config.yml file (default: ./config.yml or "
                    "$INGENIOUS_PROJECT_PATH)"
                ),
            ),
        ] = None,
        profile: Annotated[
            Optional[str],
            typer.Option(
                "--profile",
                "-p",
                help=(
                    "Path to profiles.yml file (default: ./profiles.yml or "
                    "$INGENIOUS_PROFILE_PATH)"
                ),
            ),
        ] = None,
        host: Annotated[
            str,
            typer.Option(
                "--host", "-h", help="Host to bind the server (default: 0.0.0.0)"
            ),
        ] = DEFAULT_LOCAL_HOST,
        port: Annotated[
            int,
            typer.Option(
                "--port", help="Port to bind the server (default: 80 or $WEB_PORT)"
            ),
        ] = int(os.getenv("WEB_PORT", str(DEFAULT_PORT))),
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
            project_dir=config,
            profile_dir=profile,
            host=host,
            port=port,
        )

    # Keep old command for backward compatibility
    @app.command(hidden=True)
    def run_rest_api_server(
        project_dir: Annotated[
            Optional[str],
            typer.Argument(help="The path to the config file. "),
        ] = None,
        profile_dir: Annotated[
            Optional[str],
            typer.Argument(
                help=(
                    "The path to the profile file. If left blank it will use "
                    "'./profiles.yml' if it exists, otherwise "
                    "'$HOME/.ingenious/profiles.yml'"
                )
            ),
        ] = None,
        host: Annotated[
            str,
            typer.Argument(
                help=(
                    "The host to run the server on. Default is 127.0.0.1. For "
                    "docker or external access use 0.0.0.0"
                )
            ),
        ] = DEFAULT_LOCAL_HOST,
        port: Annotated[
            int,
            typer.Argument(help="The port to run the server on. Default is 80."),
        ] = DEFAULT_PORT,
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
        if project_dir is not None:
            os.environ["INGENIOUS_PROJECT_PATH"] = project_dir
        elif os.getenv("INGENIOUS_PROJECT_PATH") is None:
            # Default to config.yml in current directory
            default_config_path = Path.cwd() / "config.yml"
            if default_config_path.exists():
                os.environ["INGENIOUS_PROJECT_PATH"] = str(default_config_path)
                logger.info(
                    "Using default config path",
                    config_path=str(default_config_path),
                    operation="config_discovery",
                )

        # Profiles.yml is deprecated - prioritize .env configuration
        # Only use profiles.yml if explicitly provided via CLI argument
        if profile_dir is not None:
            # Explicit profile path provided via CLI
            profile_dir = str(Path(profile_dir))
            if os.path.exists(profile_dir):
                logger.info(
                    "Using explicitly provided profiles.yml",
                    profile_path=str(profile_dir),
                    operation="profile_setup",
                )
                os.environ["INGENIOUS_PROFILE_PATH"] = str(profile_dir).replace(
                    "\\", "/"
                )
            else:
                logger.warning(
                    "Specified profiles.yml not found, using .env configuration only",
                    profile_path=str(profile_dir),
                    operation="profile_setup",
                )
        else:
            # No explicit profile specified - skip profiles.yml and use .env only
            logger.info(
                "Profiles.yml is deprecated. Using .env configuration only.",
                operation="profile_setup",
            )
            # Ensure INGENIOUS_PROFILE_PATH is not set to avoid legacy loading
            if "INGENIOUS_PROFILE_PATH" in os.environ:
                del os.environ["INGENIOUS_PROFILE_PATH"]

        config = get_config()

        # Resolve host/port at call time so env monkeypatching in tests is honored.
        resolved_host, resolved_port = resolve_host_port(
            host_flag=host, port_flag=port
        )
        # Apply resolved values to the runtime configuration used by uvicorn.
        config.web_configuration.ip_address = resolved_host
        config.web_configuration.port = resolved_port

        # Ensure FastAPI app observes the environment already set above
        os.environ["LOADENV"] = "False"
        console.print(
            f"Running all elements of the project in {project_dir}", style="info"
        )

        # If the code has been pip installed then recursively copy the ingenious
        # folder into the site-packages directory.
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
            """Log available modules under a namespace for diagnostics."""
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
        ] = DEFAULT_TUNER_PORT,
        host: Annotated[
            str,
            typer.Option(
                "--host",
                "-h",
                help="Host to bind the prompt tuner (default: 127.0.0.1)",
            ),
        ] = DEFAULT_LOCAL_HOST,
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
