"""Verify CLI help messages for the 'azure-search' command group.

This module contains integration tests that confirm the `azure-search` Typer
subcommand and its children (like 'run') are correctly registered with the main
CLI application. It validates that help text (`--help`) is generated correctly
and includes all expected commands and options. This ensures the CLI remains
discoverable and self-documenting for end-users.
"""

from __future__ import annotations

import inspect
import os
import re
import sys
from typing import TYPE_CHECKING, Any

from typer.testing import CliRunner, Result

if TYPE_CHECKING:
    from typer import Typer


def _collect_cli_debug() -> str:
    """Gather extensive debug info about the CLI app state for error reporting.

    This function introspects the application's environment, dependencies, and
    Typer registration state. It exists to provide rich, actionable context in
    pytest failure messages, which is crucial for diagnosing complex issues related
    to command discovery and CLI wiring.
    """
    lines: list[str | Any] = []
    lines.append("=== ENV & VERSIONS ===")
    lines.append(f"PYTHONPATH={os.environ.get('PYTHONPATH')}")
    lines.append(f"sys.executable={sys.executable}")
    lines.append(f"sys.path[:5]={sys.path[:5]}")
    try:
        import click
        import typer

        lines.append(
            f"typer={getattr(typer, '__version__', '?')}, click={getattr(click, '__version__', '?')}"
        )
    except Exception as e:
        lines.append(f"typer/click import error: {e!r}")

    # Root app introspection
    lines.append("\n=== ROOT APP INTROSPECTION ===")
    try:
        from ingenious.cli import main as main_mod

        lines.append(
            f"ingenious.cli.main file={inspect.getsourcefile(main_mod) or inspect.getfile(main_mod)}"
        )
        app: Typer = main_mod.app
        reg_cmds: list[Any] | None = getattr(app, "registered_commands", None)
        reg_grps: list[Any] | None = getattr(app, "registered_groups", None)
        if reg_cmds is not None:
            lines.append(
                f"root.registered_commands={[getattr(c, 'name', '?') for c in reg_cmds]}"
            )
        else:
            lines.append("root.registered_commands not present on app")

        if reg_grps is not None:
            lines.append(
                f"root.registered_groups={[getattr(g, 'name', '?') for g in reg_grps]}"
            )
        else:
            lines.append("root.registered_groups not present on app")
    except Exception as e:
        lines.append(f"root app introspection error: {e!r}")

    # Azure-search sub-app introspection
    lines.append("\n=== AZURE-SEARCH SUBAPP INTROSPECTION ===")
    try:
        from ingenious.services.azure_search import (
            cli as az_cli,
        )

        az_file: str = inspect.getsourcefile(az_cli) or inspect.getfile(az_cli)
        lines.append(f"ingenious.services.azure_search.cli file={az_file}")
        az_app: Typer | None = getattr(az_cli, "app", None)
        lines.append(f"azure_search.cli.app exists={bool(az_app)}")
        if az_app is not None:
            az_cmds: list[Any] | None = getattr(az_app, "registered_commands", None)
            az_grps: list[Any] | None = getattr(az_app, "registered_groups", None)
            if az_cmds is not None:
                lines.append(
                    f"azure.registered_commands={[getattr(c, 'name', '?') for c in az_cmds]}"
                )
            if az_grps is not None:
                lines.append(
                    f"azure.registered_groups={[getattr(g, 'name', '?') for g in az_grps]}"
                )
    except Exception as e:
        lines.append(f"azure-search import/introspection error: {e!r}")

    # Registry introspection (best effort; field names may differ)
    lines.append("\n=== REGISTRY INTROSPECTION ===")
    try:
        from ingenious.cli import registry as reg_mod

        reg_file: str = inspect.getsourcefile(reg_mod) or inspect.getfile(reg_mod)
        lines.append(f"registry module file={reg_file}")
        reg_obj: Any = getattr(reg_mod, "registry", None) or getattr(
            reg_mod, "REGISTRY", None
        )
        if reg_obj:
            try:
                lines.append(f"registry attrs={list(vars(reg_obj).keys())}")
                # Try common internals
                for key in ("_modules", "_commands", "modules", "commands"):
                    if hasattr(reg_obj, key):
                        val: Any = getattr(reg_obj, key)
                        length: int | str
                        try:
                            length = len(val)  # list/dict/set
                        except Exception:
                            length = "n/a"
                        lines.append(
                            f"registry.{key} type={type(val).__name__} len={length}"
                        )
            except Exception as e:
                lines.append(f"registry vars() error: {e!r}")
        else:
            lines.append("registry object not found (no 'registry' or 'REGISTRY').")
    except Exception as e:
        lines.append(f"registry import/introspection error: {e!r}")

    # Help outputs
    lines.append("\n=== HELP OUTPUTS ===")
    try:
        from ingenious.cli.main import app

        r: Result = CliRunner().invoke(app, ["--help"])
        lines.append("--- root --help ---")
        lines.append(r.stdout)
        lines.append(f"exit_code={r.exit_code}")
    except Exception as e:
        lines.append(f"root help invoke error: {e!r}")

    try:
        from ingenious.cli.main import app

        r = CliRunner().invoke(app, ["azure-search", "run", "--help"])
        lines.append("--- azure-search run --help ---")
        lines.append(r.stdout)
        lines.append(f"exit_code={r.exit_code}")
    except Exception as e:
        lines.append(f"azure run help invoke error: {e!r}")

    return "\n".join(str(x) for x in lines)


def test_root_help_shows_azure_search() -> None:
    """Verify the 'azure-search' command appears in the root --help output.

    This test ensures that the azure-search subcommand is correctly registered
    with the main Typer application and is therefore discoverable by users.
    """
    from ingenious.cli.main import app

    runner = CliRunner()
    result: Result = runner.invoke(app, ["--help"])

    if result.exit_code != 0 or not re.search(r"\bazure-search\b", result.stdout):
        import pytest

        debug: str = _collect_cli_debug()
        pytest.fail("Expected 'azure-search' in root help.\n\n" + debug)

    # still assert to keep coverage accurate if the early fail didn't trigger
    assert result.exit_code == 0
    assert re.search(r"\bazure-search\b", result.stdout)


def test_azure_search_has_run_help() -> None:
    """Verify the 'azure-search run --help' output includes expected flags.

    This test confirms that the 'run' command's parameters are correctly
    defined and exposed in the help text, ensuring users know what options
    are available.
    """
    from ingenious.cli.main import app

    runner = CliRunner()
    result: Result = runner.invoke(app, ["azure-search", "run", "--help"])

    flags: list[str] = [
        "--search-endpoint",
        "--search-key",
        "--search-index-name",
        "--openai-endpoint",
        "--openai-key",
        "--embedding-deployment",
        "--generation-deployment",
    ]
    missing: list[str] = [flag for flag in flags if flag not in result.stdout]

    if result.exit_code != 0 or missing:
        import pytest

        debug: str = _collect_cli_debug()
        pytest.fail(
            f"'azure-search run --help' missing flags: {missing} "
            f"or bad exit ({result.exit_code}).\n\n{debug}"
        )

    # still assert to keep coverage accurate if the early fail didn't trigger
    assert result.exit_code == 0
    for flag in flags:
        assert flag in result.stdout
