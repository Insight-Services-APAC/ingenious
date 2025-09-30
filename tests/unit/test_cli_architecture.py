"""
Tests for the CLI architecture components.

This module tests the BaseCommand class, CommandRegistry, and shared utilities
to ensure the refactored CLI architecture works correctly.
"""

import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
from rich.console import Console

from ingenious.cli.base import BaseCommand, CommandError, ExitCode
from ingenious.cli.commands.help import HelpCommand, StatusCommand
from ingenious.cli.registry import CommandRegistry
from ingenious.cli.utilities import FileOperations, ValidationUtils


class TestCommand(BaseCommand):
    """Test command implementation for testing BaseCommand."""

    def execute(self, test_arg: str = "default", **kwargs: Any) -> str:
        """Test execute method."""
        return f"executed with {test_arg}"


class FailingCommand(BaseCommand):
    """Test command that raises exceptions."""

    def execute(self, should_fail: bool = True, **kwargs: Any) -> None:
        """Test execute method that fails."""
        if should_fail:
            raise CommandError("Test error", ExitCode.VALIDATION_ERROR)


class TestBaseCommand:
    """Test cases for BaseCommand class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.console = Mock(spec=Console)
        self.console.get_time = Mock(return_value=0.0)
        self.console.is_jupyter = False
        self.console.is_interactive = True
        self.console.__enter__ = Mock(return_value=self.console)
        self.console.__exit__ = Mock(return_value=None)
        self.command = TestCommand(self.console)

    def test_command_initialization(self):
        """Test that BaseCommand initializes correctly."""
        assert self.command.console == self.console
        assert hasattr(self.command, "logger")
        assert self.command._progress is None

    def test_successful_execution(self):
        """Test successful command execution."""
        result = self.command.run(test_arg="test_value")
        assert result == "executed with test_value"

    def test_command_error_handling(self):
        """Test that CommandError is handled correctly."""
        failing_command = FailingCommand(self.console)

        with pytest.raises(Exception):  # typer.Exit or click.exceptions.Exit
            failing_command.run(should_fail=True)

    def test_print_methods(self):
        """Test that print methods call console correctly."""
        self.command.print_success("success message")
        self.command.print_error("error message")
        self.command.print_warning("warning message")
        self.command.print_info("info message")

        # Verify console.print was called
        assert self.console.print.call_count >= 4

    @patch("rich.progress.Progress")
    def test_progress_methods(self, mock_progress_class):
        """Test progress tracking methods."""
        mock_progress = Mock()
        mock_progress_class.return_value = mock_progress

        # Test start progress
        progress = self.command.start_progress("Testing...")
        assert progress is not None
        assert self.command._progress is not None

        # Test stop progress
        self.command.stop_progress()
        assert self.command._progress is None

    def test_load_env_file_with_path(self, tmp_path, monkeypatch):
        """Test loading environment variables from a provided .env file."""
        env_file = tmp_path / ".env.custom"
        env_file.write_text("TEST_ENV_VALUE=123\n")

        monkeypatch.delenv("TEST_ENV_VALUE", raising=False)

        resolved = self.command.load_env_file(str(env_file))

        assert resolved == str(env_file.resolve())
        assert os.getenv("TEST_ENV_VALUE") == "123"

    def test_load_env_file_missing_path(self, tmp_path):
        """Test that missing environment files raise a CommandError."""
        missing = tmp_path / "does-not-exist.env"

        with pytest.raises(CommandError) as exc:
            self.command.load_env_file(str(missing))

        assert "Environment file not found" in str(exc.value)


class TestCommandRegistry:
    """Test cases for CommandRegistry class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.console = Mock(spec=Console)
        self.registry = CommandRegistry(self.console)

    def test_registry_initialization(self):
        """Test that CommandRegistry initializes correctly."""
        assert self.registry.console == self.console
        assert len(self.registry._commands) == 0
        assert len(self.registry._registered_modules) == 0

    def test_register_command(self):
        """Test command registration."""
        self.registry.register_command(
            "test", TestCommand, "Test command", "test_module"
        )

        assert "test" in self.registry._commands
        command_info = self.registry.get_command("test")
        assert command_info.name == "test"
        assert command_info.command_class == TestCommand
        assert command_info.description == "Test command"

    def test_register_command_conflict(self):
        """Test command registration conflict handling."""
        # Register first command
        self.registry.register_command("test", TestCommand, "First command")

        # Try to register conflicting command
        with pytest.raises(ValueError):
            self.registry.register_command("test", TestCommand, "Second command")

    def test_register_command_force_override(self):
        """Test force overriding command registration."""
        # Register first command
        self.registry.register_command("test", TestCommand, "First command")

        # Force override
        self.registry.register_command(
            "test", FailingCommand, "Second command", force=True
        )

        command_info = self.registry.get_command("test")
        assert command_info.command_class == FailingCommand

    def test_list_commands(self):
        """Test command listing."""
        self.registry.register_command("test1", TestCommand, "Test 1")
        self.registry.register_command("test2", FailingCommand, "Test 2", hidden=True)

        # Test listing visible commands
        visible_commands = self.registry.list_commands(include_hidden=False)
        assert len(visible_commands) == 1
        assert visible_commands[0].name == "test1"

        # Test listing all commands
        all_commands = self.registry.list_commands(include_hidden=True)
        assert len(all_commands) == 2


class TestFileOperations:
    """Test cases for FileOperations utility class."""

    def test_ensure_directory(self):
        """Test directory creation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_dir = Path(temp_dir) / "test_subdir"

            result = FileOperations.ensure_directory(test_dir)

            assert result == test_dir
            assert test_dir.exists()
            assert test_dir.is_dir()

    def test_copy_tree_safe(self):
        """Test safe directory tree copying."""
        with tempfile.TemporaryDirectory() as temp_dir:
            src_dir = Path(temp_dir) / "source"
            dst_dir = Path(temp_dir) / "destination"

            # Create source structure
            src_dir.mkdir()
            (src_dir / "file.txt").write_text("content")

            result = FileOperations.copy_tree_safe(src_dir, dst_dir)

            assert result is True
            assert dst_dir.exists()
            assert (dst_dir / "file.txt").exists()


class TestValidationUtils:
    """Test cases for ValidationUtils utility class."""

    def test_validate_port(self):
        """Test port validation."""
        # Valid ports
        assert ValidationUtils.validate_port(80)[0] is True
        assert ValidationUtils.validate_port("8080")[0] is True
        assert ValidationUtils.validate_port(65535)[0] is True

        # Invalid ports
        assert ValidationUtils.validate_port(0)[0] is False
        assert ValidationUtils.validate_port(65536)[0] is False
        assert ValidationUtils.validate_port("not_a_number")[0] is False

    def test_validate_url(self):
        """Test URL validation."""
        # Valid URLs
        assert ValidationUtils.validate_url("https://example.com")[0] is True
        assert ValidationUtils.validate_url("http://localhost:8080")[0] is True

        # Invalid URLs
        assert ValidationUtils.validate_url("not_a_url")[0] is False
        assert ValidationUtils.validate_url("")[0] is False


class TestHelpCommand:
    """Test cases for HelpCommand."""

    def setup_method(self):
        """Set up test fixtures."""
        self.console = Mock(spec=Console)
        self.command = HelpCommand(self.console)

    def test_general_help(self):
        """Test general help display."""
        self.command.execute()

        # Verify console.print was called multiple times
        assert self.console.print.call_count > 0

    def test_specific_help_topics(self):
        """Test specific help topics."""
        topics = ["setup", "workflows", "config", "deployment"]

        for topic in topics:
            self.console.reset_mock()
            self.command.execute(topic=topic)
            assert self.console.print.call_count > 0

    def test_invalid_help_topic(self):
        """Test invalid help topic handling."""
        with pytest.raises(CommandError):
            self.command.execute(topic="invalid_topic")


class TestStatusCommand:
    """Test cases for StatusCommand."""

    def setup_method(self):
        """Set up test fixtures."""
        self.console = Mock(spec=Console)
        self.command = StatusCommand(self.console)

    @patch.dict(
        os.environ,
        {
            "INGENIOUS_MODELS__0__API_KEY": "test-key",
            "INGENIOUS_MODELS__0__BASE_URL": "https://example.com",
            "INGENIOUS_MODELS__0__MODEL": "gpt-4o-mini",
        },
    )
    @patch("pathlib.Path.exists")
    def test_status_check(self, mock_exists):
        """Test status checking."""
        mock_exists.return_value = True

        self.command.execute()

        # Verify console output was generated
        assert self.console.print.call_count > 0


# Run tests if script is executed directly
if __name__ == "__main__":
    pytest.main([__file__])
