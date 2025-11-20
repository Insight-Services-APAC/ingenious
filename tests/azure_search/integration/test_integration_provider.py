"""Run end-to-end integration tests for Azure Search provider.

This module contains integration tests that verify the AzureSearchProvider's
functionality against live Azure Search and Azure OpenAI services. It is
designed to catch issues related to authentication, network configuration,
API changes, or schema drift in the search index.

These tests require specific environment variables to be set with credentials
and endpoints for the Azure services. They will be skipped automatically if
the required variables are not found.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterable

pytestmark = pytest.mark.azure_integration

REQUIRED_ENV: list[str] = [
    "AZURE_SEARCH_ENDPOINT",
    "AZURE_SEARCH_KEY",
    "AZURE_SEARCH_INDEX_NAME",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_KEY",
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
    "AZURE_OPENAI_GENERATION_DEPLOYMENT",
]

# Optional; if not present we default to a commonly used stable version.
DEFAULT_OPENAI_API_VERSION: str = "2024-06-01"


def _require_env(keys: Iterable[str]) -> dict[str, str]:
    """Check for and return required environment variables.

    Skips the current test via pytest.skip if any of the specified
    environment variable keys are missing. This ensures that integration
    tests only run when the necessary configuration is present.

    Args:
        keys: An iterable of environment variable names to check.

    Returns:
        A dictionary mapping the required keys to their values.
    """
    missing: list[str] = [k for k in keys if not os.getenv(k)]
    if missing:
        pytest.skip(f"Skipping: missing env vars: {', '.join(missing)}")
    return {k: os.environ[k] for k in keys}


def _lazy_imports() -> tuple[Any, Any, Any]:
    """Import and return core components for the test.

    This function defers the import of project-specific modules until runtime
    within a test function. This prevents pytest collection from failing with
    ImportError if the modules are not available in the test environment,
    making the test suite more robust to path or dependency issues.
    """
    try:
        from ingenious.services.azure_search.provider import AzureSearchProvider
    except Exception as e:
        pytest.skip(f"Cannot import AzureSearchProvider: {e}")

    try:
        from ingenious.services.azure_search.builders import (
            build_search_config_from_settings,
        )
    except Exception as e:
        pytest.skip(f"Cannot import build_search_config_from_settings: {e}")

    try:
        from ingenious.settings import IngeniousSettings
    except Exception as e:
        pytest.skip(f"Cannot import IngeniousSettings: {e}")

    return AzureSearchProvider, build_search_config_from_settings, IngeniousSettings


@pytest.mark.asyncio
async def test_end_to_end_provider_with_real_service_no_semantic() -> None:
    """Test the AzureSearchProvider against a live service without semantic ranking.

    This end-to-end test validates the provider's ability to connect to Azure,
    authenticate, and perform a basic vector search query. It specifically
    configures the provider to disable semantic ranking to test the baseline
    retrieval functionality.
    """
    env: dict[str, str] = _require_env(REQUIRED_ENV)
    AzureSearchProvider: Any
    build_from_settings: Any
    IngeniousSettings: Any
    AzureSearchProvider, build_from_settings, IngeniousSettings = _lazy_imports()

    api_version: str = os.getenv("AZURE_OPENAI_API_VERSION", DEFAULT_OPENAI_API_VERSION)

    # Build a minimal, valid settings object that your builder understands.
    # If your settings schema differs, tweak these keys accordingly.
    settings: Any = IngeniousSettings(
        models=[
            {
                "provider": "azure",
                "family": "openai",
                "type": "embedding",
                "api_base": env["AZURE_OPENAI_ENDPOINT"],
                "api_key": env["AZURE_OPENAI_KEY"],
                "api_version": api_version,
                "deployment": env["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"],
            },
            {
                "provider": "azure",
                "family": "openai",
                "type": "chat",
                "api_base": env["AZURE_OPENAI_ENDPOINT"],
                "api_key": env["AZURE_OPENAI_KEY"],
                "api_version": api_version,
                "deployment": env["AZURE_OPENAI_GENERATION_DEPLOYMENT"],
            },
        ],
        azure_search_services=[
            {
                "endpoint": env["AZURE_SEARCH_ENDPOINT"],
                "api_key": env["AZURE_SEARCH_KEY"],
                "index_name": env["AZURE_SEARCH_INDEX_NAME"],
                # Explicitly disable semantic ranking for this test
                "enable_semantic_ranking": False,
            }
        ],
    )

    config: Any = build_from_settings(settings)
    provider: Any = AzureSearchProvider(config)

    try:
        results: list[Any] = await provider.retrieve("smoke query", top_k=1)
        assert isinstance(results, list)
    finally:
        # Make sure we close network clients even if the assertion fails.
        await provider.close()


@pytest.mark.asyncio
async def test_end_to_end_provider_with_real_service_with_semantic() -> None:
    """Test the AzureSearchProvider against a live service with semantic ranking.

    This end-to-end test validates the provider's functionality when semantic
    ranking is enabled. It requires the `AZURE_SEARCH_SEMANTIC_CONFIG`
    environment variable to be set to the name of a valid semantic
    configuration in the target search index. The test is skipped if this
    variable is not provided.
    """
    env: dict[str, str] = _require_env(REQUIRED_ENV)
    semantic_name: str | None = os.getenv("AZURE_SEARCH_SEMANTIC_CONFIG")
    if not semantic_name:
        pytest.skip("Skipping: AZURE_SEARCH_SEMANTIC_CONFIG not set")

    AzureSearchProvider: Any
    build_from_settings: Any
    IngeniousSettings: Any
    AzureSearchProvider, build_from_settings, IngeniousSettings = _lazy_imports()

    api_version: str = os.getenv("AZURE_OPENAI_API_VERSION", DEFAULT_OPENAI_API_VERSION)

    settings: Any = IngeniousSettings(
        models=[
            {
                "provider": "azure",
                "family": "openai",
                "type": "embedding",
                "api_base": env["AZURE_OPENAI_ENDPOINT"],
                "api_key": env["AZURE_OPENAI_KEY"],
                "api_version": api_version,
                "deployment": env["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"],
            },
            {
                "provider": "azure",
                "family": "openai",
                "type": "chat",
                "api_base": env["AZURE_OPENAI_ENDPOINT"],
                "api_key": env["AZURE_OPENAI_KEY"],
                "api_version": api_version,
                "deployment": env["AZURE_OPENAI_GENERATION_DEPLOYMENT"],
            },
        ],
        azure_search_services=[
            {
                "endpoint": env["AZURE_SEARCH_ENDPOINT"],
                "api_key": env["AZURE_SEARCH_KEY"],
                "index_name": env["AZURE_SEARCH_INDEX_NAME"],
                "enable_semantic_ranking": True,
                "semantic_configuration_name": semantic_name,
            }
        ],
    )

    config: Any = build_from_settings(settings)
    provider: Any = AzureSearchProvider(config)

    try:
        results: list[Any] = await provider.retrieve("smoke query", top_k=1)
        assert isinstance(results, list)
    finally:
        await provider.close()
