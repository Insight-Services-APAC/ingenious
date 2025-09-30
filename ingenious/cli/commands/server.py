"""
Server-related CLI commands for Insight Ingenious.

This module contains commands for starting and managing the API server.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Optional

from ingenious.cli.base import BaseCommand, CommandError, ExitCode
from ingenious.cli.utilities import ValidationUtils

if TYPE_CHECKING:
    import typer
    from rich.console import Console


class ServeCommand(BaseCommand):
    """Start the API server with web interface."""

    def execute(
        self,
        env_file: Optional[str] = None,
        host: str = "127.0.0.1",
        port: Optional[int] = None,
        no_prompt_tuner: bool = False,
        **kwargs: object,
    ) -> None:
        """
        Start the Insight Ingenious API server with web interface.

        Args:
            env_file: Optional path to a .env file to load before starting
            host: Host to bind the server
            port: Port to bind the server
            no_prompt_tuner: Whether to disable the prompt tuner interface
        """
        # Resolve port
        if port is None:
            port = int(os.getenv("WEB_PORT", "80"))

        # Validate port
        is_valid_port, port_error = ValidationUtils.validate_port(port)
        if not is_valid_port:
            raise CommandError(f"Invalid port: {port_error}", ExitCode.VALIDATION_ERROR)

        # Load optional environment file before starting the server
        try:
            self.load_env_file(env_file)
        except CommandError:
            self.print_error("Failed to load environment configuration")
            self._show_config_help()
            raise

        self.start_progress("Starting API server...")

        try:
            # Import and start the server
            import uvicorn

            from ingenious.config.main_settings import IngeniousSettings
            from ingenious.main import create_app

            # Load settings
            settings = IngeniousSettings()
            app = create_app(settings)

            self.stop_progress()
            self.print_success(f"Starting server on {host}:{port}")

            # Start the server
            uvicorn.run(app, host=host, port=port)

        except ImportError as e:
            self.stop_progress()
            raise CommandError(
                f"Failed to import server dependencies: {e}",
                ExitCode.MISSING_DEPENDENCY,
            )
        except Exception as e:
            self.stop_progress()
            raise CommandError(f"Failed to start server: {e}", ExitCode.GENERAL_ERROR)

    def _show_config_help(self) -> None:
        """Show configuration help for server startup."""
        self.console.print(
            "\n[bold yellow]💡 Configuration Requirements:[/bold yellow]"
        )
        self.console.print("1. Copy .env.example to .env and fill in required values")
        self.console.print("   cp .env.example .env")
        self.console.print("2. Set required INGENIOUS_* environment variables, e.g.")
        self.console.print("   export INGENIOUS_MODELS__0__API_KEY=your-key")
        self.console.print(
            "   export INGENIOUS_MODELS__0__BASE_URL=https://your-endpoint"
        )
        self.console.print(
            "3. Optionally use --env-file to load a specific .env configuration"
        )


# Backward compatibility
def register_commands(app: typer.Typer, console: Console) -> None:
    """Register server-related commands with the typer app."""
    from typing_extensions import Annotated

    @app.command(name="serve", help="Start the API server with web interface")
    def serve(
        env_file: Annotated[
            Optional[str],
            typer.Option(
                "--env-file",
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
        """Start the Insight Ingenious API server with web interface."""
        cmd = ServeCommand(console)
        cmd.run(
            env_file=env_file,
            host=host,
            port=port,
            no_prompt_tuner=no_prompt_tuner,
        )
