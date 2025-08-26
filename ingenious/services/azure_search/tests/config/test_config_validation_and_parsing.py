"""Test extra validators and complex field parsing for configuration models.

This module contains tests for the custom validation logic and field parsing
within the Pydantic settings models in `ingenious.config`. It specifically
targets validators that enforce cross-field dependencies, complex constraints,
and the parsing of nested dictionary structures (from environment variables)
into lists of model instances.

These tests ensure that configuration loading is robust and fails early with
clear errors for invalid or incomplete settings.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import ValidationError

from ingenious.common.enums import AuthenticationMethod
from ingenious.config import get_config
from ingenious.config.main_settings import IngeniousSettings
from ingenious.config.models import (
    AzureSearchSettings,
    LoggingSettings,
    ModelSettings,
    WebSettings,
)

if TYPE_CHECKING:
    from _pytest.logging import LogCaptureFixture
    from pytest import MonkeyPatch


# ─────────────────────────────────────────────────────────────────────────────
# ModelSettings
# ─────────────────────────────────────────────────────────────────────────────


def test_modelsettings_client_id_and_secret_require_all_fields_or_env(
    monkeypatch: MonkeyPatch,
) -> None:
    """Test that CLIENT_ID_AND_SECRET auth allows env vars to satisfy requirements.

    This test verifies that if a required field for client secret authentication
    (like `tenant_id`) is missing from the direct configuration, the validator
    will correctly allow the model to be created if the corresponding environment
    variable is set.
    """
    # Tenant ID missing on the object, but present via AZURE_TENANT_ID env → allowed
    monkeypatch.setenv("AZURE_TENANT_ID", "tenant-123")

    ms = ModelSettings(
        model="gpt-4o",
        base_url="https://oai.example.com",
        deployment="chat",
        authentication_method=AuthenticationMethod.CLIENT_ID_AND_SECRET,
        client_id="cid",
        client_secret="csecret",
        tenant_id="",  # intentionally missing — satisfied via env var
    )
    assert ms.client_id == "cid"
    assert ms.client_secret == "csecret"
    # Clean up (pytest monkeypatch auto-cleans, but keep intent explicit)
    monkeypatch.delenv("AZURE_TENANT_ID", raising=False)


@pytest.mark.parametrize(
    "base_url,should_raise",
    [
        ("https://ok.example.com", False),
        ("http://ok.example.com", False),
        ("ftp://bad.example.com", True),  # invalid scheme
        ("PLACEHOLDER", True),  # forbidden placeholder pattern
        ("", False),  # empty is allowed (validator only checks when value is provided)
    ],
)
def test_modelsettings_base_url_validation(base_url: str, should_raise: bool) -> None:
    """Test `base_url` validation for correct schemes and forbidden values.

    Ensures that the `base_url` field only accepts valid HTTP/HTTPS URLs and rejects
    common placeholder values that indicate a configuration error. An empty value
    is permitted to allow for cases where it's not needed.
    """
    kwargs: dict[str, str] = dict(
        model="gpt-4o",
        deployment="chat",
        api_key="",  # not using TOKEN auth here
    )
    if should_raise:
        with pytest.raises(ValidationError):
            ModelSettings(base_url=base_url, **kwargs)
    else:
        ms = ModelSettings(base_url=base_url, **kwargs)
        assert ms.base_url == base_url


# ─────────────────────────────────────────────────────────────────────────────
# LoggingSettings
# ─────────────────────────────────────────────────────────────────────────────


def test_logging_level_normalization_and_reject_unknown() -> None:
    """Test that log levels are normalized to lowercase and invalid levels are rejected.

    This ensures configuration is case-insensitive (e.g., "DEBUG" becomes "debug")
    and that only valid log level names recognized by the `logging` module are
    accepted, preventing runtime errors from misconfigured levels.
    """
    ls = LoggingSettings(root_log_level="DEBUG", log_level="WARNING")
    assert ls.root_log_level == "debug"
    assert ls.log_level == "warning"

    with pytest.raises(ValidationError):
        LoggingSettings(root_log_level="verbose")  # unknown level


# ─────────────────────────────────────────────────────────────────────────────
# WebSettings
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("port", [0, -1, 65536])
def test_websettings_port_bounds_invalid(port: int) -> None:
    """Test that out-of-bounds port numbers raise a validation error.

    Ensures the `port` number for the web server is within the valid TCP/IP
    range (1-65535).
    """
    with pytest.raises(ValidationError):
        WebSettings(port=port)


@pytest.mark.parametrize("port", [1, 80, 443, 65535])
def test_websettings_port_bounds_valid(port: int) -> None:
    """Test that valid port numbers are accepted.

    Verifies that common and edge-case valid port numbers are correctly
    accepted by the `WebSettings` model.
    """
    ws = WebSettings(port=port)
    assert ws.port == port


# ─────────────────────────────────────────────────────────────────────────────
# IngeniousSettings field parsing (dict → list)
# ─────────────────────────────────────────────────────────────────────────────


def test_ingenioussettings_parse_models_from_nested_env_dict() -> None:
    """Test parsing of `models` from a dict into a sorted list of `ModelSettings`.

    Pydantic-settings reads nested environment variables (e.g., INGENIOUS_MODELS_0_MODEL)
    into a dictionary. This test ensures our custom parser correctly converts this
    dictionary into a list of `ModelSettings` objects, sorted by their numeric keys.
    """
    # Provide 'models' as a dict that mimics nested env-structure keys
    models_dict: dict[str, dict[str, str]] = {
        "1": {
            "model": "gpt-4o",
            "api_type": "rest",
            "api_version": "2024-02-01",
            "deployment": "chat",
            "base_url": "https://oai.example.com",
        },
        "0": {
            "model": "text-embedding-3-small",
            "api_type": "rest",
            "api_version": "2024-02-01",
            "deployment": "embed",
            "base_url": "https://oai.example.com",
        },
    }
    s = IngeniousSettings(models=models_dict)
    assert len(s.models) == 2
    # Keys are sorted; "0" should come before "1"
    assert s.models[0].model == "text-embedding-3-small"
    assert s.models[1].model == "gpt-4o"


def test_ingenioussettings_parse_azure_search_from_nested_env_dict() -> None:
    """Test parsing `azure_search_services` from a dict into a list of `AzureSearchSettings`.

    Similar to the models parsing test, this verifies that a dictionary of Azure
    Search service configurations is correctly transformed into a list of
    `AzureSearchSettings` instances.
    """
    models_dict: dict[str, dict[str, str]] = {
        "0": {
            "model": "gpt-4o",
            "api_type": "rest",
            "api_version": "2024-02-01",
            "deployment": "chat",
            "base_url": "https://oai.example.com",
        }
    }
    azure_dict: dict[str, dict[str, Any]] = {
        "0": {
            "service": "svc",
            "endpoint": "https://search.example.net",
            "key": "sk",
            "index_name": "idx",
            "use_semantic_ranking": True,
            "top_k_retrieval": 15,
        }
    }
    s = IngeniousSettings(models=models_dict, azure_search_services=azure_dict)
    assert s.azure_search_services is not None
    assert len(s.azure_search_services) == 1
    az0 = s.azure_search_services[0]
    assert isinstance(az0, AzureSearchSettings.__class__) or hasattr(az0, "index_name")
    assert az0.index_name == "idx"
    assert az0.top_k_retrieval == 15
    assert az0.use_semantic_ranking is True


# ─────────────────────────────────────────────────────────────────────────────
# get_config() logging + re-raise on validation error
# ─────────────────────────────────────────────────────────────────────────────


def test_get_config_logs_and_reraises_on_validation_error(
    monkeypatch: MonkeyPatch, caplog: LogCaptureFixture
) -> None:
    """Test that `get_config` logs an error and re-raises on configuration failure.

    This ensures that when `IngeniousSettings` fails to initialize (e.g., due to
    a validation error), the `get_config` utility function catches the exception,
    logs a helpful error message, and then re-raises the original exception to
    halt application startup.
    """
    # Patch logger factory to return a standard logger we can capture with caplog
    import logging as _logging

    def fake_get_logger(_name: str) -> logging.Logger:
        """Return a test logger instance."""
        return _logging.getLogger("ing-config-test")

    monkeypatch.setattr(
        "ingenious.core.structured_logging.get_logger",
        fake_get_logger,
        raising=True,
    )

    # Force IngeniousSettings() to raise in constructor so get_config logs and re-raises
    class BoomSettings:
        def __init__(self, *a: Any, **k: Any) -> None:
            """Raise an exception to simulate a Pydantic validation failure."""
            raise RuntimeError("boom-config")

    monkeypatch.setattr(
        "ingenious.config.IngeniousSettings", BoomSettings, raising=True
    )

    with caplog.at_level(logging.ERROR, logger="ing-config-test"):
        with pytest.raises(RuntimeError, match="boom-config"):
            get_config()

    # Ensure our error message was logged
    messages: list[str] = [rec.getMessage() for rec in caplog.records]
    assert any("Failed to load configuration: boom-config" in m for m in messages)
