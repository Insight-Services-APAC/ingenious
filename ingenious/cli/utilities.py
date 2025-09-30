"""
Utility functions and classes for the CLI.

This module contains helper functions and classes used by various CLI commands,
providing common operations, file handling, validation, and formatting utilities.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from sysconfig import get_paths
from typing import Any, Dict, Optional, Union

from rich.panel import Panel
from rich.table import Table

import ingenious.utils.stage_executor as stage_executor_module
from ingenious.core.structured_logging import get_logger
from ingenious.utils.imports import import_class_with_fallback

logger = get_logger(__name__)


class CliFunctions:
    """Utility functions for CLI operations."""

    class RunTestBatch(stage_executor_module.IActionCallable):
        """Action callable for running test batches."""

        async def __call__(self, progress: Any, task_id: Any, **kwargs: Any) -> None:
            module_name = "tests.run_tests"
            class_name = "RunBatches"
            try:
                repository_class_import = import_class_with_fallback(
                    module_name, class_name
                )
                repository_class = repository_class_import(
                    progress=progress, task_id=task_id
                )

                await repository_class.run()

            except (ImportError, AttributeError) as e:
                raise ValueError(f"Batch Run Failed: {module_name}") from e

    @staticmethod
    def PureLibIncludeDirExists() -> bool:
        """Check if the ingenious package exists in site-packages."""
        ChkPath = Path(get_paths()["purelib"]) / Path("ingenious/")
        return os.path.exists(ChkPath)

    @staticmethod
    def copy_ingenious_folder(src: Union[str, Path], dst: Union[str, Path]) -> None:
        """Copy the ingenious folder from source to destination."""
        if not os.path.exists(dst):
            os.makedirs(dst)  # Create the destination directory if it doesn't exist

        for item in os.listdir(src):
            src_path = os.path.join(src, item)
            dst_path = os.path.join(dst, item)

            if os.path.isdir(src_path):
                # Recursively copy subdirectories
                CliFunctions.copy_ingenious_folder(src_path, dst_path)
            else:
                # Copy files
                if not os.path.exists(dst_path) or os.path.getmtime(
                    src_path
                ) > os.path.getmtime(dst_path):
                    shutil.copy2(src_path, dst_path)  # Copy file with metadata


class FileOperations:
    """File and directory operations utilities."""

    @staticmethod
    def ensure_directory(
        path: Union[str, Path], description: str = "Directory"
    ) -> Path:
        """
        Ensure a directory exists, creating it if necessary.

        Args:
            path: Directory path
            description: Human-readable description for error messages

        Returns:
            Path object for the directory

        Raises:
            OSError: If directory cannot be created
        """
        path_obj = Path(path)
        try:
            path_obj.mkdir(parents=True, exist_ok=True)
            return path_obj
        except OSError as e:
            raise OSError(
                f"Failed to create {description.lower()} '{path}': {e}"
            ) from e

    @staticmethod
    def copy_tree_safe(
        src: Union[str, Path], dst: Union[str, Path], overwrite: bool = False
    ) -> bool:
        """
        Safely copy a directory tree.

        Args:
            src: Source directory
            dst: Destination directory
            overwrite: Whether to overwrite existing files

        Returns:
            True if copy was successful, False otherwise
        """
        src_path = Path(src)
        dst_path = Path(dst)

        if not src_path.exists():
            logger.error(f"Source directory does not exist: {src}")
            return False

        try:
            if dst_path.exists() and not overwrite:
                logger.warning(f"Destination already exists: {dst}")
                return False

            if dst_path.exists():
                shutil.rmtree(dst_path)

            shutil.copytree(src_path, dst_path)
            return True
        except OSError as e:
            logger.error(f"Failed to copy directory tree from '{src}' to '{dst}': {e}")
            return False


class ValidationUtils:
    """Validation utilities for CLI commands."""

    @staticmethod
    def validate_port(port: Union[str, int]) -> tuple[bool, Optional[str]]:
        """
        Validate that a port number is valid.

        Args:
            port: Port number to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            port_int = int(port)
            if 1 <= port_int <= 65535:
                return True, None
            else:
                return False, "Port must be between 1 and 65535"
        except ValueError:
            return False, "Port must be a valid integer"

    @staticmethod
    def validate_url(url: str) -> tuple[bool, Optional[str]]:
        """
        Validate that a URL is properly formatted.

        Args:
            url: URL to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            from urllib.parse import urlparse

            result = urlparse(url)
            if all([result.scheme, result.netloc]):
                return True, None
            else:
                return False, "Invalid URL format"
        except Exception as e:
            return False, f"URL validation error: {e}"


class OutputFormatters:
    """Utilities for formatting CLI output."""

    @staticmethod
    def create_status_table(items: Dict[str, Any], title: str = "Status") -> Table:
        """
        Create a formatted table for status information.

        Args:
            items: Dictionary of status items
            title: Table title

        Returns:
            Rich Table object
        """
        table = Table(title=title, show_header=True, header_style="bold blue")
        table.add_column("Item", style="cyan", width=25)
        table.add_column("Status", width=15)
        table.add_column("Details", style="dim")

        for key, value in items.items():
            if isinstance(value, dict):
                status = value.get("status", "Unknown")
                details = value.get("details", "")
                status_style = OutputFormatters._get_status_style(status)
                table.add_row(
                    key, f"[{status_style}]{status}[/{status_style}]", details
                )
            else:
                table.add_row(key, str(value), "")

        return table

    @staticmethod
    def _get_status_style(status: str) -> str:
        """Get Rich style for status values."""
        status_lower = status.lower()
        if status_lower in ["ok", "success", "passed", "valid"]:
            return "green"
        elif status_lower in ["error", "failed", "invalid"]:
            return "red"
        elif status_lower in ["warning", "missing", "partial"]:
            return "yellow"
        else:
            return "blue"

    @staticmethod
    def create_info_panel(content: str, title: str, style: str = "blue") -> Panel:
        """
        Create an informational panel.

        Args:
            content: Panel content
            title: Panel title
            style: Panel border style

        Returns:
            Rich Panel object
        """
        return Panel(content, title=title, border_style=style)
