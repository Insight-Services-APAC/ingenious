"""Test the server command-line interface commands.

This module contains unit tests for the `serve` command defined in
`ingenious.cli.server_commands`. It verifies that command-line arguments,
environment variables, and configuration file settings are correctly handled
and prioritized when launching the web server. The tests use mocks to isolate
the CLI logic from the actual server and configuration loading.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import typer
from typer.testing import CliRunner, Result

import ingenious.cli.server_commands as server_module

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import MonkeyPatch


runner: CliRunner = CliRunner()


def make_app_and_register() -> typer.Typer:
    """Create a Typer app and register the server commands onto it.

    This helper function centralizes the setup of the Typer application
    for tests, ensuring a consistent and clean app instance for each test case.
    """
    app: typer.Typer = typer.Typer()
    console: MagicMock = MagicMock()
    server_module.register_commands(app, console)
    return app


def stub_config(ip: str = "0.0.0.0", port: int = 80) -> SimpleNamespace:
    """Create a mock configuration object for testing.

    This function produces a simplified configuration object that mimics the
    structure accessed by the server startup logic, avoiding the need for a
    full configuration file load.
    """
    # Mimic the fields accessed by the server code
    web_conf = SimpleNamespace(ip_address=ip, port=port)
    cfg = SimpleNamespace(web_configuration=web_conf)
    return cfg


def test_serve_env_port_precedence(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Test that the WEB_PORT environment variable sets the server port.

    This test verifies that when the `serve` command is run without a `--port`
    argument, the port is sourced from the `WEB_PORT` environment variable,
    demonstrating correct precedence of environment variables over defaults.
    """
    # Set ENV before registering commands (default evaluated at declaration time)
    monkeypatch.setenv("WEB_PORT", "1234")

    app: typer.Typer = make_app_and_register()

    # Patch get_config, make_app seam, uvicorn.run
    with (
        patch("ingenious.cli.server_commands.get_config", return_value=stub_config()) as get_cfg,
        patch("ingenious.cli.server_commands.make_app", return_value=MagicMock()) as make_app_mock,
        patch("ingenious.cli.server_commands.uvicorn.run") as uv_run,
    ):
        result: Result = runner.invoke(app, ["serve"])
        assert result.exit_code == 0

        # config loaded and app constructed via seam
        get_cfg.assert_called_once()
        make_app_mock.assert_called_once_with(get_cfg.return_value)

        # uvicorn called with env-provided port (1234) and default host "0.0.0.0"
        args: tuple[Any, ...]
        kwargs: dict[str, Any]
        args, kwargs = uv_run.call_args
        assert kwargs["host"] == "0.0.0.0"
        assert kwargs["port"] == 1234

        # LOADENV flipped
        assert os.environ.get("LOADENV") == "False"


def test_serve_cli_port_overrides_env(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Test that CLI arguments for port and host override environment variables.

    This test confirms that when `--port` and `--host` arguments are provided
    to the `serve` command, their values take precedence over any conflicting
    settings from environment variables, ensuring direct user input is respected.
    """
    # ENV present, but CLI overrides
    monkeypatch.setenv("WEB_PORT", "1234")

    app: typer.Typer = make_app_and_register()

    with (
        patch("ingenious.cli.server_commands.get_config", return_value=stub_config()) as get_cfg,
        patch("ingenious.cli.server_commands.make_app", return_value=MagicMock()) as make_app_mock,
        patch("ingenious.cli.server_commands.uvicorn.run") as uv_run,
    ):
        result: Result = runner.invoke(app, ["serve", "--port", "9999", "--host", "127.0.0.1"])
        assert result.exit_code == 0

        # app constructed via seam
        make_app_mock.assert_called_once_with(get_cfg.return_value)

        args: tuple[Any, ...]
        kwargs: dict[str, Any]
        args, kwargs = uv_run.call_args
        assert kwargs["host"] == "127.0.0.1"
        assert kwargs["port"] == 9999

        # ensure server called
        uv_run.assert_called_once()


def test_serve_env_file_loading(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Test that providing --env-file triggers dotenv loading with the given path."""
    env_file: Path = tmp_path / ".env.runtime"
    env_file.write_text("CUSTOM_ENV=from-file\n")

    monkeypatch.delenv("CUSTOM_ENV", raising=False)

    app: typer.Typer = make_app_and_register()

    with (
        patch("ingenious.cli.server_commands.load_dotenv") as mock_load_dotenv,
        patch("ingenious.cli.server_commands.get_config", return_value=stub_config()) as get_cfg,
        patch("ingenious.cli.server_commands.make_app", return_value=MagicMock()) as make_app_mock,
        patch("ingenious.cli.server_commands.uvicorn.run") as uv_run,
    ):

        def _fake_load(path=None, override=True):
            if path:
                os.environ["CUSTOM_ENV"] = "loaded"

        mock_load_dotenv.side_effect = _fake_load

        result: Result = runner.invoke(app, ["serve", "--env-file", str(env_file)])
        assert result.exit_code == 0

        # ensure dotenv called with resolved path
        called_paths = [str(call.args[0]) for call in mock_load_dotenv.call_args_list if call.args]
        assert str(env_file.resolve()) in called_paths
        assert any(call.kwargs.get("override") for call in mock_load_dotenv.call_args_list)

        # ensure environment variable was set via fake loader
        assert os.environ.get("CUSTOM_ENV") == "loaded"

        # server still starts
        uv_run.assert_called_once()
        make_app_mock.assert_called_once_with(get_cfg.return_value)
