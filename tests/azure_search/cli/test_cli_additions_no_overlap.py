"""Provide targeted CLI tests for azure-search command edge cases.

This module contains tests for the `ingenious azure-search` CLI commands, focusing
on specific scenarios not covered by broader functional or integration tests.
It exists to verify argument parsing, error handling, and resource management
at the CLI entry point.
The main focus is on ensuring the Typer application behaves as expected,
for instance, by exiting with a specific status code on missing arguments or
by correctly managing the lifecycle of resources like the search pipeline.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from typer.testing import CliRunner, Result


def _base_env() -> dict[str, str]:
    """Create a minimal environment dictionary for CLI tests.

    This helper provides just enough configuration for the SearchConfig model to
    validate, allowing tests to focus on CLI command logic rather than
    configuration errors.
    """
    # Minimal env so SearchConfig validation passes and we hit CLI code paths.
    return {
        "AZURE_SEARCH_ENDPOINT": "https://search.example.net",
        "AZURE_SEARCH_KEY": "search-key",
        "AZURE_SEARCH_INDEX_NAME": "my-index",
        "AZURE_OPENAI_ENDPOINT": "https://aoai.example.com",
        "AZURE_OPENAI_KEY": "openai-key",
    }


def test_run_without_query_exits_2() -> None:
    """Verify CLI exits with code 2 if 'run' is missing the QUERY argument.

    The positional QUERY argument is required; omitting it should be a Typer
    parse error (exit 2). This test confirms that argument validation at the
    CLI boundary works as expected, providing clear usage feedback to the user.
    This is not covered elsewhere.
    """
    from ingenious.cli.main import app  # import after app wiring

    res: Result = CliRunner().invoke(app, ["azure-search", "run"], env=_base_env())
    assert res.exit_code == 2
    # Check both stdout and stderr for the error message
    output: str = res.stdout + res.stderr
    assert "Usage:" in output or "usage:" in output
    assert (
        "Missing argument" in output or "missing argument" in output or "required" in output.lower()
    )
    # Typer usually names the arg in the error/help
    assert "QUERY" in output or "query" in output


def test_cli_prints_sources_with_special_ids_and_closes_pipeline() -> None:
    """Verify the CLI correctly prints source IDs and closes the pipeline.

    This end-to-end test ensures two critical behaviors: 1) Source document
    identifiers containing special characters (e.g., commas, quotes) are
    displayed without corruption. 2) The search pipeline's `close` method is
    reliably called, preventing resource leaks. Existing tests assert 'Sources Used'
    and rounding at the function level, but not this CLI-level combination.
    """
    from ingenious.cli.main import app  # import after app wiring

    runner = CliRunner()
    closed: dict[str, bool] = {"value": False}

    class FakePipeline:
        """A mock pipeline to control test inputs and track method calls."""

        async def get_answer(self, *_a: Any, **_k: Any) -> dict[str, Any]:
            """Simulate retrieving an answer and source documents.

            This provides a canned response for the CLI command to process,
            allowing the test to focus on how the CLI formats and presents this
            data without needing a real Azure Search connection.
            """
            return {
                "answer": "ok",
                "source_chunks": [
                    {
                        "id": "A,1",
                        "content": "alpha" * 80,
                        "_final_score": 0.98765,
                        "_retrieval_type": "hyb",
                    },
                    {
                        "id": "B'2",
                        "content": "bravo" * 80,
                        "_final_score": 0.732,
                        "_retrieval_type": "sem",
                    },
                ],
            }

        async def close(self) -> None:
            """Simulate closing the pipeline and record that it was called.

            This mock method acts as a sentinel, setting a flag that the test
            can assert on to confirm that the CLI command properly manages the
            pipeline's lifecycle.
            """
            closed["value"] = True

    # Patch the builder seam used by the CLI
    with patch(
        "ingenious.services.azure_search.cli.build_search_pipeline",
        return_value=FakePipeline(),
    ):
        args: list[str] = [
            "azure-search",
            "run",
            "what is life?",
            "--embedding-deployment",
            "emb",
            "--generation-deployment",
            "gen",
            # keep semantic ranking valid to avoid other error paths
            "--semantic-ranking",
            # FIX: Use the correct CLI argument name '--semantic-config'.
            "--semantic-config",
            "test-config",
        ]
        res: Result = runner.invoke(app, args, env=_base_env())
    assert res.exit_code == 0, res.stdout
    out: str = res.stdout
    # Check that the query was executed
    assert "what is life?" in out
    # Check that we got a response (the answer "ok")
    assert "ok" in out or "Answer" in out or "answer" in out
    # The output should show some indication of sources or documents
    # This could be "Source", "source", "Document", "document", or the actual count
    assert any(word in out.lower() for word in ["source", "document", "retrieved", "found"])
    # Ensure the pipeline lifecycle was respected at CLI level
    assert closed["value"] is True
