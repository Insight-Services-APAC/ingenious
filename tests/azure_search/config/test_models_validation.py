"""Test configuration model validation for Ingenious settings.

This module contains tests to ensure that the Pydantic models within
the Ingenious configuration system correctly validate and prioritize
environment variables. It specifically covers edge cases like mixing
JSON string configurations with nested environment variables and validates
constraints on numeric fields like network ports.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from ingenious.config.main_settings import IngeniousSettings

if TYPE_CHECKING:
    from pytest import MonkeyPatch


def test_parse_models_json_and_nested_mix(monkeypatch: MonkeyPatch) -> None:
    """Verify JSON string env var overrides nested model configurations.

    This test ensures that when `INGENIOUS_MODELS` is set as a JSON
    string, it is parsed and used exclusively, ignoring any conflicting
    nested environment variables (e.g., `INGENIOUS_MODELS__1__MODEL`).
    This confirms the intended priority of configuration sources.
    """
    # Configuration via JSON string should override nested variables
    models_json: str = json.dumps(
        [
            {
                "model": "gpt-5",
                "api_key": "k",
                "base_url": "https://oai/",
                "deployment": "chat",
            }
        ]
    )
    monkeypatch.setenv("INGENIOUS_MODELS", models_json)
    # These nested variables should be ignored
    monkeypatch.setenv("INGENIOUS_MODELS__1__MODEL", "text-embedding-3-small")
    monkeypatch.setenv("INGENIOUS_MODELS__1__API_KEY", "k2")
    monkeypatch.setenv("INGENIOUS_MODELS__1__BASE_URL", "https://oai/")
    monkeypatch.setenv("INGENIOUS_MODELS__1__DEPLOYMENT", "embed")

    settings: IngeniousSettings = IngeniousSettings()
    # Expect only the model from the JSON string
    assert len(settings.models) == 1
    assert settings.models[0].deployment == "chat"


def test_web_settings_port_range(monkeypatch: MonkeyPatch) -> None:
    """Test that the web server port is validated to be within the valid range.

    This test checks that the `IngeniousSettings` model raises a `ValueError`
    if the web configuration port is set to a value outside the standard
    valid TCP/IP port range (1-65535). It checks both the lower and upper
    out-of-bounds conditions, as well as a valid port.
    """
    # minimal valid model
    monkeypatch.setenv("INGENIOUS_MODELS__0__MODEL", "gpt-5")
    monkeypatch.setenv("INGENIOUS_MODELS__0__API_KEY", "k")
    monkeypatch.setenv("INGENIOUS_MODELS__0__BASE_URL", "https://oai/")
    monkeypatch.setenv("INGENIOUS_MODELS__0__DEPLOYMENT", "chat")

    # lower bound
    monkeypatch.setenv("INGENIOUS_WEB_CONFIGURATION__PORT", "0")
    with pytest.raises(ValueError):
        IngeniousSettings()

    monkeypatch.setenv("INGENIOUS_WEB_CONFIGURATION__PORT", "65536")
    with pytest.raises(ValueError):
        IngeniousSettings()

    monkeypatch.setenv("INGENIOUS_WEB_CONFIGURATION__PORT", "443")
    s: IngeniousSettings = IngeniousSettings()
    assert s.web_configuration.port == 443
