"""CLI contract tests for the Azure Search service integration.

This module validates the command-line interface for the `azure-search run`
command, ensuring its public contract remains stable. The tests verify
critical aspects of the CLI's behavior, such as the presence of required flags
in the help text, to prevent accidental breaking changes for users.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

if TYPE_CHECKING:
    from click.testing import Result


def test_azure_search_run_help_lists_required_flags() -> None:
    """Verify `azure-search run --help` output includes all required flags.

    This contract test ensures the command's user-facing interface does not
    change unexpectedly. It confirms that all critical connection flags are
    documented in the help output, which serves as the public API definition.
    """
    from ingenious.cli.main import app  # import after app wiring

    runner: CliRunner = CliRunner()
    res: Result = runner.invoke(app, ["azure-search", "run", "--help"])
    assert res.exit_code == 0, res.stdout

    out: str = res.stdout
    required: list[str] = [
        "--search-endpoint",
        "--search-key",
        "--search-index-name",
        "--openai-endpoint",
        "--openai-key",
        "--embedding-deployment",
        "--generation-deployment",
    ]
    missing: list[str] = [flag for flag in required if flag not in out]
    assert not missing, f"Missing flags in help: {missing}\n\n{out}"
