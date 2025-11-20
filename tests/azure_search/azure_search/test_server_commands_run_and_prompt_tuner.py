"""Provide additional tests for CLI server commands.

This module contains tests for edge cases and specific behaviors of the
`ingenious.cli.server_commands` module. It focuses on interactions with
environment variables, default configuration path detection, and the handling
of deprecated or removed commands. These tests supplement the primary
command tests to ensure robust real-world behavior.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Callable, cast
from unittest.mock import MagicMock, patch

import typer
from rich.console import Console
from typer.testing import CliRunner

import ingenious.cli.server_commands as server_module

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import MonkeyPatch
    from typer.testing import Result


runner = CliRunner()


def make_app_and_register(console: Console | MagicMock | None = None) -> typer.Typer:
    """Create a minimal Typer app and register server commands.

    This helper function isolates the app creation and command registration
    logic, allowing tests to easily create a fresh app instance with mocked
    dependencies for focused testing.
    """
    app = typer.Typer()
    console = console or MagicMock()
    server_module.register_commands(app, console)
    return app


def stub_config(ip: str = "0.0.0.0", port: int = 80) -> SimpleNamespace:
    """Create a minimal stub for the application configuration.

    This function returns a SimpleNamespace object that mimics the structure
    of the real configuration, providing just enough attributes for the server
    commands to access without needing a full configuration setup.
    """
    web_conf = SimpleNamespace(ip_address=ip, port=port)
    cfg = SimpleNamespace(web_configuration=web_conf)
    return cfg


def test_serve_uses_WEB_PORT_env_when_set(monkeypatch: MonkeyPatch) -> None:
    """Ensure the 'serve' command uses the WEB_PORT env var for its default port."""
    # This test verifies that environment variables are correctly used to
    # configure command-line defaults when no explicit arguments are provided.
    # The default value is captured at command registration time, so the
    # environment must be set before the app is created.
    # Clean state and set env BEFORE registering commands (default captured at registration)
    monkeypatch.setenv("WEB_PORT", "1234")

    app: typer.Typer = make_app_and_register()

    with (
        patch("ingenious.cli.server_commands.get_config", return_value=stub_config()) as get_cfg,
        patch("ingenious.cli.server_commands.make_app", return_value=MagicMock()) as make_app_mock,
        patch("ingenious.cli.server_commands.uvicorn.run") as uv_run,
    ):
        result: Result = runner.invoke(app, ["serve"])
        assert result.exit_code == 0

        # App constructed and uvicorn called with WEB_PORT
        make_app_mock.assert_called_once_with(get_cfg.return_value)
        kwargs: dict[str, Any]
        _, kwargs = uv_run.call_args
        assert kwargs["host"] == "0.0.0.0"
        assert kwargs["port"] == 1234
        # Env side‑effect enforced by command
        assert os.environ.get("LOADENV") == "False"


def test_serve_cli_port_overrides_env(monkeypatch: MonkeyPatch) -> None:
    """Ensure CLI --port overrides WEB_PORT and --host overrides the default."""
    # This ensures that explicit command-line arguments have a higher precedence
    # than configuration from environment variables, which is standard CLI behavior.
    monkeypatch.setenv("WEB_PORT", "1234")

    app: typer.Typer = make_app_and_register()

    with (
        patch("ingenious.cli.server_commands.get_config", return_value=stub_config()) as get_cfg,
        patch("ingenious.cli.server_commands.make_app", return_value=MagicMock()) as make_app_mock,
        patch("ingenious.cli.server_commands.uvicorn.run") as uv_run,
    ):
        result: Result = runner.invoke(app, ["serve", "--port", "9999", "--host", "127.0.0.1"])
        assert result.exit_code == 0

        make_app_mock.assert_called_once_with(get_cfg.return_value)
        kwargs: dict[str, Any]
        _, kwargs = uv_run.call_args
        assert kwargs["host"] == "127.0.0.1"
        assert kwargs["port"] == 9999


def test_run_rest_api_server_loads_env_files(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """Ensure 'run-rest-api-server' triggers dotenv loading with and without --env-file."""
    monkeypatch.chdir(tmp_path)
    app: typer.Typer = make_app_and_register()

    fake_logger: MagicMock = MagicMock()
    monkeypatch.setattr("ingenious.cli.server_commands.logger", fake_logger, raising=False)

    monkeypatch.setattr(
        "ingenious.cli.server_commands.CliFunctions.PureLibIncludeDirExists",
        cast(Callable[[], bool], lambda: False),
        raising=False,
    )

    env_file = tmp_path / ".env.runtime"
    env_file.write_text("INGENIOUS_MODELS__0__MODEL=gpt-4o-mini\n")

    with (
        patch("ingenious.cli.server_commands.load_dotenv") as mock_load_dotenv,
        patch("ingenious.cli.server_commands.get_config", return_value=stub_config()) as get_cfg,
        patch("ingenious.cli.server_commands.make_app", return_value=MagicMock()) as make_app_mock,
        patch("ingenious.cli.server_commands.uvicorn.run") as uv_run,
    ):
        # A) No args → default dotenv discovery (no positional args)
        res1: Result = runner.invoke(app, ["run-rest-api-server"])
        assert res1.exit_code == 0
        assert any(
            not call.args and call.kwargs.get("override")
            for call in mock_load_dotenv.call_args_list
        )

        mock_load_dotenv.reset_mock()

        # B) Provide explicit env file → should load resolved path
        res2: Result = runner.invoke(app, ["run-rest-api-server", str(env_file)])
        assert res2.exit_code == 0
        called_paths = [str(call.args[0]) for call in mock_load_dotenv.call_args_list if call.args]
        assert str(env_file.resolve()) in called_paths

        # App seam still used
        make_app_mock.assert_called()
        uv_run.assert_called()
        get_cfg.assert_called()


def test_prompt_tuner_removed_exits_1_with_message() -> None:
    """Test the removed 'prompt-tuner' command exits with a message and status 1."""
    # This ensures that commands removed in newer versions fail gracefully
    # by informing the user of the removal and suggesting an alternative,
    # rather than failing with an "unknown command" error.
    app = typer.Typer()
    console = Console()
    server_module.register_commands(app, console)

    result: Result = runner.invoke(app, ["prompt-tuner"])
    assert result.exit_code == 1
    # Rich markup preserved in output; assert on key substrings
    assert "Starting prompt tuner at http://127.0.0.1:5000" in result.stdout
    assert "Prompt tuner has been removed from this version" in result.stdout
    assert "Use the main API server instead: ingen serve" in result.stdout
