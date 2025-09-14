"""Server-related CLI commands for Insight Ingenious.

This module defines the Typer CLI commands that start and manage the API server.
It centralizes host/port resolution so tests and deployments get consistent
behavior. When a deploy-style port is configured via `WEB_PORT` or `PORT`, the
server binds to `0.0.0.0` unless an explicit `--host` override is provided.
CLI flags always take precedence over environment values.

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
from typing import TYPE_CHECKING

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

# Load environment variables from .env file *once* at import time.
load_dotenv()

# Initialize module logger
logger = get_logger(__name__)

# -----------------------
# Module-level constants
# -----------------------
DEFAULT_LOCAL_HOST = "127.0.0.1"
BIND_ALL_HOST = "0.0.0.0"
DEFAULT_PORT = 80
DEFAULT_TUNER_PORT = 5000


def resolve_host_port(host_flag: str | None, port_flag: int | None) -> tuple[str, int]:
    """Resolve the (host, port) pair honoring env precedence and CLI overrides.

    Why:
        Tests and deploy environments often provide `WEB_PORT`/`PORT`. When such
        an env port is present and `--host` is not explicitly set, we bind to
        `0.0.0.0` to expose the service externally (container/PaaS semantics).

    Args:
        host_flag: Host provided via CLI (or None if omitted).
        port_flag: Port provided via CLI (or None if omitted).

    Returns:
        A `(host, port)` pair suitable for `uvicorn.run(...)`.
    """
    env_web: str | None = os.getenv("WEB_PORT")
    env_proc: str | None = os.getenv("PORT")

    env_port: int | None = None
    for cand in (env_web, env_proc):
        if cand is None:
            continue
        try:
            env_port = int(cand)
            break
        except ValueError:
            # Ignore non-integer env values
            continue

    # Port precedence: CLI > ENV > DEFAULT
    port: int = port_flag if port_flag is not None else (env_port or DEFAULT_PORT)

    # Host precedence:
    # - If CLI host is provided, use it.
    # - Else if an env port is present, bind to 0.0.0.0 (externally visible).
    # - Else fall back to loopback.
    if host_flag is not None:
        host: str = host_flag
    else:
        host = BIND_ALL_HOST if env_port is not None else DEFAULT_LOCAL_HOST

    return host, port


def make_app(config: "IngeniousSettings") -> "FastAPI":
    """Create and return the FastAPI application for the given configuration.

    Why:
        This import is intentionally late so environment variables (set by the
        CLI prior to calling this function) are honored by the app factory.

    Args:
        config: The loaded application settings.

    Returns:
        A configured FastAPI instance.
    """
    from ingenious.main import create_app

    return create_app(config)


def register_commands(app: typer.Typer, console: Console) -> None:
    """Register server-related commands with the provided Typer app.

    Why:
        Centralized registration keeps CLI surface coherent and ensures
        consistent default/precedence behavior across commands.

    Args:
        app: The Typer application to register the commands on.
        console: Rich console used for user-facing messages.
    """

    @app.command(name="serve", help="Start the API server with web interface")
    def serve(
        config: Annotated[
            str | None,
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
            str | None,
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
            str | None,
            typer.Option(
                "--host",
                "-h",
                help="Host to bind (default: auto; CLI overrides env/config)",
            ),
        ] = None,
        port: Annotated[
            int | None,
            typer.Option(
                "--port",
                help="Port to bind (default: from $WEB_PORT/$PORT or config)",
            ),
        ] = None,
        no_prompt_tuner: Annotated[
            bool,
            typer.Option(
                "--no-prompt-tuner",
                help="Disable the prompt tuner interface",
            ),
        ] = False,
    ) -> None:
        """Start the Insight Ingenious API server with web interface.

        Why:
            The command resolves host/port at runtime so environment variables
            set by tests or deployments are respected. CLI flags always win.

        Notes:
            The prompt tuner UI may be disabled via `--no-prompt-tuner`.

        Raises:
            typer.Exit: On early validation or termination conditions.
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
            str | None,
            typer.Argument(help="The path to the config file."),
        ] = None,
        profile_dir: Annotated[
            str | None,
            typer.Argument(
                help=(
                    "The path to the profile file. If left blank it will use "
                    "'./profiles.yml' if it exists, otherwise "
                    "'$HOME/.ingenious/profiles.yml'"
                )
            ),
        ] = None,
        host: Annotated[
            str | None,
            typer.Argument(
                help=(
                    "Host to run the server on. Default: auto (env/config). "
                    "For docker/external access use 0.0.0.0"
                )
            ),
        ] = None,
        port: Annotated[
            int | None,
            typer.Argument(
                help=(
                    "Port to run the server on. Default: from "
                    "$WEB_PORT/$PORT or config."
                )
            ),
        ] = None,
    ) -> None:
        """Run the REST API server exposing agent workflows.

        Why:
            This hidden command is preserved for legacy/test paths. It honors
            the same host/port resolution logic as `serve`.

        Args:
            project_dir: Optional path to `config.yml` (or default discovery).
            profile_dir: Optional path to `profiles.yml` (deprecated).
            host: Host override (None → resolved at call time).
            port: Port override (None → resolved at call time).
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

        # Profiles.yml is deprecated - prioritize .env configuration.
        # Only use profiles.yml if explicitly provided via CLI argument.
        if profile_dir is not None:
            profile_dir_str = str(Path(profile_dir))
            if os.path.exists(profile_dir_str):
                logger.info(
                    "Using explicitly provided profiles.yml",
                    profile_path=profile_dir_str,
                    operation="profile_setup",
                )
                os.environ["INGENIOUS_PROFILE_PATH"] = profile_dir_str.replace(
                    "\\", "/"
                )
            else:
                logger.warning(
                    "Specified profiles.yml not found, using .env configuration only",
                    profile_path=profile_dir_str,
                    operation="profile_setup",
                )
        else:
            logger.info(
                "Profiles.yml is deprecated. Using .env configuration only.",
                operation="profile_setup",
            )
            # Ensure INGENIOUS_PROFILE_PATH is not set to avoid legacy loading
            if "INGENIOUS_PROFILE_PATH" in os.environ:
                del os.environ["INGENIOUS_PROFILE_PATH"]

        config = get_config()

        # Resolve host/port at call time so env monkeypatching in tests is honored.
        resolved_host, resolved_port = resolve_host_port(host_flag=host, port_flag=port)

        # Apply resolved values to the runtime configuration used by uvicorn.
        config.web_configuration.ip_address = resolved_host
        config.web_configuration.port = resolved_port

        # Ensure FastAPI app observes the environment already set above.
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
            """Log available modules under a namespace for diagnostics.

            Why:
                Diagnostic helper to list submodules at runtime, aiding in
                environment troubleshooting without failing the server.

            Args:
                namespace: Dotted package path to introspect.
            """
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
            except ImportError as exc:
                logger.warning(
                    "Failed to import namespace",
                    namespace=namespace,
                    error=str(exc),
                )

        os.environ["INGENIOUS_WORKING_DIR"] = str(Path(os.getcwd()))
        os.chdir(str(Path(os.getcwd())))
        log_namespace_modules(
            "ingenious.services.chat_services.multi_agent.conversation_flows"
        )

        app_fastapi = make_app(config)
        uvicorn.run(
            app_fastapi,
            host=config.web_configuration.ip_address,
            port=config.web_configuration.port,
        )

    @app.command(name="prompt-tuner", help="Start standalone prompt tuning interface")
    def prompt_tuner(
        port: Annotated[
            int,
            typer.Option(
                "--port",
                "-p",
                help="Port for the prompt tuner (default: 5000)",
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
        """Announce that the standalone prompt tuner has been removed.

        Why:
            The legacy prompt tuner is no longer supported. We keep a helpful
            command that exits with guidance so existing scripts fail clearly.

        Args:
            port: Intended port for the tuner (printed for clarity).
            host: Intended host for the tuner (printed for clarity).

        Raises:
            typer.Exit: Always raised with code 1 to signal removal.
        """
        logger.info(
            "Starting prompt tuner server",
            host=host,
            port=port,
            url=f"http://{host}:{port}",
            operation="prompt_tuner_startup",
        )
        console.print(f"Starting prompt tuner at http://{host}:{port}")
        console.print(
            "[red]Prompt tuner has been removed from this version[/red]"
        )
        console.print("Use the main API server instead: ingen serve")
        raise typer.Exit(1)
