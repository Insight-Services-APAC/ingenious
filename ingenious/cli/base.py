"""
Base command architecture for Insight Ingenious CLI.

This module provides the abstract base class and common patterns for all CLI commands,
ensuring consistent error handling, output formatting, and user feedback.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ingenious.core.structured_logging import get_logger


class ExitCode(Enum):
    """Standard exit codes for CLI commands."""

    SUCCESS = 0
    GENERAL_ERROR = 1
    INVALID_CONFIG = 2
    MISSING_DEPENDENCY = 3
    VALIDATION_ERROR = 4


class CommandError(Exception):
    """Base exception for CLI command errors."""

    def __init__(self, message: str, exit_code: ExitCode = ExitCode.GENERAL_ERROR):
        super().__init__(message)
        self.exit_code = exit_code


class BaseCommand(ABC):
    """
    Abstract base class for all CLI commands.

    Provides consistent patterns for:
    - Error handling and reporting
    - Progress indication
    - Output formatting
    - Logging
    - Exit codes
    """

    def __init__(self, console: Console):
        """Initialize the base command with a console instance."""
        self.console = console
        self.logger = get_logger(self.__class__.__name__)
        self._progress: Optional[Progress] = None

    @abstractmethod
    def execute(self, **kwargs: Any) -> Any:
        """
        Execute the command logic.

        This method should be implemented by all command subclasses
        and contain the main command logic.

        Args:
            **kwargs: Command-specific arguments

        Returns:
            Command result (if any)

        Raises:
            CommandError: For command-specific errors
        """
        pass

    def run(self, **kwargs: Any) -> Any:
        """
        Run the command with error handling and progress tracking.

        This method wraps the execute() method with consistent error handling,
        logging, and progress indication.

        Args:
            **kwargs: Command-specific arguments

        Returns:
            Command result (if any)
        """
        try:
            self.logger.debug(f"Starting command: {self.__class__.__name__}")
            result = self.execute(**kwargs)
            self.logger.debug(
                f"Command completed successfully: {self.__class__.__name__}"
            )
            return result

        except CommandError as e:
            self.handle_error(str(e), e.exit_code)

        except Exception as e:
            self.handle_error(f"Unexpected error: {str(e)}", ExitCode.GENERAL_ERROR)

    def handle_error(
        self, message: str, exit_code: ExitCode = ExitCode.GENERAL_ERROR
    ) -> None:
        """
        Handle errors with consistent formatting and logging.

        Args:
            message: Error message to display
            exit_code: Exit code to use when terminating
        """
        self.logger.error(message)
        self.print_error(message)

        if exit_code != ExitCode.SUCCESS:
            raise typer.Exit(exit_code.value)

    def print_success(self, message: str) -> None:
        """Print a success message with consistent formatting."""
        self.console.print(f"✅ {message}", style="green")

    def print_info(self, message: str) -> None:
        """Print an info message with consistent formatting."""
        self.console.print(f"ℹ️  {message}", style="info")

    def print_warning(self, message: str) -> None:
        """Print a warning message with consistent formatting."""
        self.console.print(f"⚠️  {message}", style="warning")

    def print_error(self, message: str) -> None:
        """Print an error message with consistent formatting."""
        self.console.print(f"❌ {message}", style="error")

    def start_progress(self, description: str = "Processing...") -> Progress:
        """
        Start a progress indicator.

        Args:
            description: Description text for the progress indicator

        Returns:
            Progress instance for task tracking
        """
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
            transient=True,
        )
        self._progress.start()
        self._progress.add_task(description=description)
        return self._progress

    def stop_progress(self) -> None:
        """Stop the current progress indicator."""
        if self._progress:
            self._progress.stop()
            self._progress = None

    def load_env_file(
        self, env_file: Optional[str] = None, *, override: bool = True
    ) -> Optional[str]:
        """
        Load environment variables from a .env file.

        Args:
            env_file: Optional path to the .env file. If omitted, the default
                dotenv discovery is used.
            override: Whether to override existing environment variables.

        Returns:
            The resolved environment file path if one was provided, otherwise None.

        Raises:
            CommandError: If the provided environment file does not exist.
        """
        from pathlib import Path

        try:
            from dotenv import load_dotenv
        except ImportError as exc:  # pragma: no cover - defensive guard
            raise CommandError(
                "python-dotenv is required to load environment files",
                ExitCode.MISSING_DEPENDENCY,
            ) from exc

        if env_file is None:
            load_dotenv(override=override)
            return None

        resolved_path = Path(env_file).expanduser().resolve()
        if not resolved_path.exists():
            raise CommandError(
                f"Environment file not found: {resolved_path}",
                ExitCode.INVALID_CONFIG,
            )

        load_dotenv(resolved_path, override=override)
        return str(resolved_path)
