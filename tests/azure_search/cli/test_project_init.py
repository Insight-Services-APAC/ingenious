"""Test the `ingenious project init` CLI command.

This module contains integration tests for the project initialization logic
exposed through the Typer CLI. It verifies that the command correctly creates
the necessary project boilerplate files and directories in a target location.
Tests cover scenarios with and without pre-existing template files to ensure
both default content generation and template-based copying work as expected.
It uses a temporary filesystem (`tmp_path`) and mocks (`monkeypatch`) to
isolate the tests from the actual package structure and filesystem.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import typer
from typer.testing import CliRunner, Result

import ingenious.cli.commands.project as project_module

runner: CliRunner = CliRunner()


def make_typer_app(console: Any) -> typer.Typer:
    """Create a Typer app with project commands for testing.

    This helper function isolates the app creation logic, allowing tests to
    inject a mock console object.

    Args:
        console: The mock console object to be used by the command.

    Returns:
        A Typer application instance with the project commands registered.
    """
    app: typer.Typer = typer.Typer()
    project_module.register_commands(app, console)
    return app


def test_project_init_default_creates_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify `init` creates default project files when templates are missing.

    This test checks that running `ingenious project init` in an empty directory
    successfully creates the expected directory structure and default config files
    (like `.env.example` and `Dockerfile`). It also ensures that running the
    command a second time does not overwrite existing files or raise an error.
    """
    # Run in a temp CWD
    monkeypatch.chdir(tmp_path)

    # Point the module's __file__ to a fake tree under tmp so base_path resolves here
    fake_root: Path = tmp_path / "fake_pkg_root"
    (fake_root / "ingenious_extensions_template").mkdir(
        parents=True, exist_ok=True
    )  # empty; will warn/skip
    module_file: Path = fake_root / "cli" / "commands" / "project.py"
    module_file.parent.mkdir(parents=True, exist_ok=True)
    module_file.write_text("# dummy file")
    monkeypatch.setattr(project_module, "__file__", str(module_file))

    # Patch FileOperations to do simple filesystem ops
    def copy_tree_safe(src: Path, dst: Path) -> bool:
        """Mock implementation of copy_tree_safe for testing."""
        shutil.copytree(src, dst)
        return True

    def ensure_directory(dst: Path, _: str) -> None:
        """Mock implementation of ensure_directory for testing."""
        dst.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(project_module.FileOperations, "copy_tree_safe", copy_tree_safe)
    monkeypatch.setattr(project_module.FileOperations, "ensure_directory", ensure_directory)

    # Use a basic console mock
    console: MagicMock = MagicMock()

    app: typer.Typer = make_typer_app(console)
    result: Result = runner.invoke(app, ["init"])
    assert result.exit_code == 0

    # Created directories/files
    assert (tmp_path / "tmp").is_dir()
    # No ingenious_extensions copied because template path exists but is empty; copy_tree still runs and creates dir
    # However our copy_tree copies an empty folder - still fine:
    assert (tmp_path / "ingenious_extensions").exists()

    # .env.example should be created with default content (no template present)
    env_example: Path = tmp_path / ".env.example"
    assert env_example.exists()
    assert "INGENIOUS_MODELS__0__API_KEY=your-api-key-here" in env_example.read_text()

    # Dockerfile should be created with default content (no template present)
    dockerfile: Path = tmp_path / "Dockerfile"
    assert dockerfile.exists()
    assert "FROM python:3.13-slim" in dockerfile.read_text()

    # Templates dir should exist even if source templates missing, and be empty
    tmpl_dir: Path = tmp_path / "templates" / "prompts" / "quickstart-1"
    assert tmpl_dir.is_dir()
    assert list(tmpl_dir.glob("*.jinja")) == []  # warned about missing templates

    # Running again should warn/skip and not crash
    result2: Result = runner.invoke(app, ["init"])
    assert result2.exit_code == 0
    # Files remain unchanged
    assert "INGENIOUS_MODELS__0__API_KEY=your-api-key-here" in env_example.read_text()
    assert "FROM python:3.13-slim" in dockerfile.read_text()


def test_project_init_with_templates_copies_and_skips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify `init` copies from templates when present and skips on subsequent runs.

    This test sets up a fake package structure containing template files and
    verifies that the `init` command correctly copies them to the target
    directory. It then runs the command again to ensure that existing files
    are not overwritten, confirming the command's idempotency.
    """
    monkeypatch.chdir(tmp_path)

    # Fake package root with templates
    fake_root: Path = tmp_path / "fake_pkg_root"
    base: Path = fake_root
    (base / "ingenious_extensions_template").mkdir(parents=True, exist_ok=True)
    (base / "ingenious_extensions_template" / "README.md").write_text("from-template")
    (base / "ingenious_extensions_template" / "templates").mkdir(parents=True, exist_ok=True)
    (base / "ingenious_extensions_template" / "templates" / "prompts").mkdir(
        parents=True, exist_ok=True
    )
    (base / "ingenious_extensions_template" / "templates" / "prompts" / "hello.jinja").write_text(
        "hi jinja"
    )

    (base / "config_templates").mkdir(parents=True, exist_ok=True)
    (base / "config_templates" / ".env.example").write_text(
        "INGENIOUS_MODELS__0__API_KEY=from-template"
    )

    (base / "docker_templates").mkdir(parents=True, exist_ok=True)
    (base / "docker_templates" / "Dockerfile").write_text("FROM python:3.12-slim")
    (base / "docker_templates" / ".dockerignore").write_text("__pycache__/")

    module_file: Path = fake_root / "cli" / "commands" / "project.py"
    module_file.parent.mkdir(parents=True, exist_ok=True)
    module_file.write_text("# dummy file")
    monkeypatch.setattr(project_module, "__file__", str(module_file))

    # Real copy/ensure impls safe to use against our temp FS
    def copy_tree_safe(src: Path, dst: Path) -> bool:
        """Mock implementation of copy_tree_safe for testing."""
        shutil.copytree(src, dst)
        return True

    def ensure_directory(dst: Path, _: str) -> None:
        """Mock implementation of ensure_directory for testing."""
        dst.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(project_module.FileOperations, "copy_tree_safe", copy_tree_safe)
    monkeypatch.setattr(project_module.FileOperations, "ensure_directory", ensure_directory)

    console: MagicMock = MagicMock()
    app: typer.Typer = make_typer_app(console)

    # First run copies from templates
    result: Result = runner.invoke(app, ["init"])
    assert result.exit_code == 0

    # Check copied tree
    assert (tmp_path / "ingenious_extensions" / "README.md").read_text() == "from-template"

    env_example: Path = tmp_path / ".env.example"
    assert env_example.read_text().strip() == "INGENIOUS_MODELS__0__API_KEY=from-template"

    dockerfile: Path = tmp_path / "Dockerfile"
    assert dockerfile.read_text().strip().startswith("FROM python:3.12-slim")

    # Prompts copied into quickstart-1
    qdir: Path = tmp_path / "templates" / "prompts" / "quickstart-1"
    assert (qdir / "hello.jinja").read_text() == "hi jinja"

    # Second run should skip existing targets and NOT overwrite
    result2: Result = runner.invoke(app, ["init"])
    assert result2.exit_code == 0
    # Content unchanged
    assert env_example.read_text().strip() == "INGENIOUS_MODELS__0__API_KEY=from-template"
    assert dockerfile.read_text().strip().startswith("FROM python:3.12-slim")
