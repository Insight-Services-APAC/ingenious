"""Test the main application settings model for Ingenious.

This module contains unit tests for the IngeniousSettings Pydantic model,
ensuring that configuration can be loaded correctly from various environment
variable formats (JSON strings, nested variables) and that validation
rules for models, services, and other parameters are properly enforced.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from ingenious.config.main_settings import IngeniousSettings

if TYPE_CHECKING:
    from pytest import MonkeyPatch


def test_models_and_azure_search_from_json_env(monkeypatch: MonkeyPatch) -> None:
    """Test that settings load correctly from JSON-encoded environment variables.

    This ensures that Pydantic's JSON decoding for complex fields works as
    expected for both the models and Azure search service configurations.
    """
    # Provide models via JSON string
    models_json: str = json.dumps(
        [
            {
                "model": "gpt-5",
                "api_key": "k1",
                "base_url": "https://oai.example.com/",
                "deployment": "chat",
                "api_version": "2024-02-01",
            },
            {
                "model": "text-embedding-3-small",
                "api_key": "k1",
                "base_url": "https://oai.example.com/",
                "deployment": "embed",
                "api_version": "2024-02-01",
            },
        ]
    )
    azure_json: str = json.dumps(
        [
            {
                "service": "svc",
                "endpoint": "https://search.example.net",
                "key": "sk",
                "index_name": "idx",
                "use_semantic_ranking": True,
                "top_k_retrieval": 15,
            }
        ]
    )
    monkeypatch.setenv("INGENIOUS_MODELS", models_json)
    monkeypatch.setenv("INGENIOUS_AZURE_SEARCH_SERVICES", azure_json)

    settings = IngeniousSettings()
    assert len(settings.models) == 2
    assert settings.models[0].model == "gpt-5"
    assert settings.azure_search_services and settings.azure_search_services[0].index_name == "idx"
    assert settings.azure_search_services[0].top_k_retrieval == 15


def test_models_and_azure_search_from_nested_env(monkeypatch: MonkeyPatch) -> None:
    """Test that settings load correctly from nested environment variables.

    This verifies that Pydantic's nested environment variable parsing
    (using "__" as a separator) works for lists of complex objects.
    """
    # Nested env for models
    monkeypatch.setenv("INGENIOUS_MODELS__0__MODEL", "gpt-5")
    monkeypatch.setenv("INGENIOUS_MODELS__0__API_KEY", "k")
    monkeypatch.setenv("INGENIOUS_MODELS__0__BASE_URL", "https://oai/")
    monkeypatch.setenv("INGENIOUS_MODELS__0__DEPLOYMENT", "chat")
    monkeypatch.setenv("INGENIOUS_MODELS__0__API_VERSION", "2024-02-01")

    # Azure Search nested
    monkeypatch.setenv("INGENIOUS_AZURE_SEARCH_SERVICES__0__SERVICE", "svc")
    monkeypatch.setenv("INGENIOUS_AZURE_SEARCH_SERVICES__0__ENDPOINT", "https://s.net")
    monkeypatch.setenv("INGENIOUS_AZURE_SEARCH_SERVICES__0__KEY", "sk")
    monkeypatch.setenv("INGENIOUS_AZURE_SEARCH_SERVICES__0__INDEX_NAME", "idx")
    monkeypatch.setenv("INGENIOUS_AZURE_SEARCH_SERVICES__0__USE_SEMANTIC_RANKING", "true")
    monkeypatch.setenv("INGENIOUS_AZURE_SEARCH_SERVICES__0__TOP_K_RETRIEVAL", "25")

    settings = IngeniousSettings()
    assert settings.models[0].deployment == "chat"
    assert (
        settings.azure_search_services
        and settings.azure_search_services[0].endpoint == "https://s.net"
    )
    assert settings.azure_search_services[0].top_k_retrieval == 25


def test_invalid_port_and_log_level(monkeypatch: MonkeyPatch) -> None:
    """Test that invalid port and log level values raise ValueErrors.

    This ensures that the validators on simple fields like port numbers and
    log levels are triggered correctly during settings instantiation.
    """
    # minimal valid model
    monkeypatch.setenv("INGENIOUS_MODELS__0__MODEL", "gpt-5")
    monkeypatch.setenv("INGENIOUS_MODELS__0__API_KEY", "k")
    monkeypatch.setenv("INGENIOUS_MODELS__0__BASE_URL", "https://oai/")
    monkeypatch.setenv("INGENIOUS_MODELS__0__DEPLOYMENT", "chat")

    # Invalid port
    monkeypatch.setenv("INGENIOUS_WEB_CONFIGURATION__PORT", "70000")
    with pytest.raises(ValueError):
        IngeniousSettings()

    # Fix port, break log level
    monkeypatch.delenv("INGENIOUS_WEB_CONFIGURATION__PORT", raising=False)
    monkeypatch.setenv("INGENIOUS_LOGGING__ROOT_LOG_LEVEL", "verbose")
    with pytest.raises(ValueError):
        IngeniousSettings()


def test_empty_models_rejected(monkeypatch: MonkeyPatch) -> None:
    """Test that configuration fails validation if no models are provided."""
    # Explicitly set models to an empty list to override any .env files
    monkeypatch.setenv("INGENIOUS_MODELS", "[]")

    # The validator raises a ValueError, so the test should expect that specifically
    # FIX: Update the match string to reflect the actual error message.
    with pytest.raises(ValueError, match="At least one model must be configured"):
        IngeniousSettings()


def test_model_auth_client_credentials_require_fields(
    monkeypatch: MonkeyPatch,
) -> None:
    """Test 'client_id_and_secret' auth requires necessary fields.

    This test confirms the validation logic for Azure client credential flow,
    ensuring that client_id, client_secret, and tenant_id (either directly or
    via the AZURE_TENANT_ID fallback) are all present.
    """
    # Succeeds when client_id/secret & tenant provided (via env var or field)
    monkeypatch.setenv("INGENIOUS_MODELS__0__MODEL", "gpt-5")
    monkeypatch.setenv("INGENIOUS_MODELS__0__BASE_URL", "https://oai/")
    monkeypatch.setenv("INGENIOUS_MODELS__0__DEPLOYMENT", "chat")
    monkeypatch.setenv("INGENIOUS_MODELS__0__AUTHENTICATION_METHOD", "client_id_and_secret")
    monkeypatch.setenv("INGENIOUS_MODELS__0__CLIENT_ID", "cid")
    monkeypatch.setenv("INGENIOUS_MODELS__0__CLIENT_SECRET", "csecret")
    # Provide tenant through AZURE_TENANT_ID env (allowed)
    monkeypatch.setenv("AZURE_TENANT_ID", "tenantX")
    settings = IngeniousSettings()
    assert settings.models[0].client_id == "cid"

    # Now missing tenant_id and AZURE_TENANT_ID -> should fail
    monkeypatch.setenv("INGENIOUS_MODELS__0__MODEL", "gpt-5")
    monkeypatch.setenv("INGENIOUS_MODELS__0__BASE_URL", "https://oai/")
    monkeypatch.setenv("INGENIOUS_MODELS__0__DEPLOYMENT", "chat")
    monkeypatch.setenv("INGENIOUS_MODELS__0__AUTHENTICATION_METHOD", "client_id_and_secret")
    monkeypatch.setenv("INGENIOUS_MODELS__0__CLIENT_ID", "cid")
    monkeypatch.setenv("INGENIOUS_MODELS__0__CLIENT_SECRET", "csecret")
    monkeypatch.delenv("AZURE_TENANT_ID", raising=False)
    with pytest.raises(ValueError):
        IngeniousSettings()
