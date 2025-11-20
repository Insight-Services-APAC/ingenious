# -- coding: utf-8 --
"""Tests the Azure Search configuration builder functions.

This module provides unit tests for the configuration builders responsible
for creating an Azure Search client configuration from the application's main
settings. It ensures that required fields are validated, settings are mapped
correctly, and that the model selection logic (for embedding and generation)
behaves as expected.

The main functions tested are `build_search_config_from_settings` and the
internal helper `_pick_models`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from ingenious.config.main_settings import IngeniousSettings
from ingenious.config.models import AzureSearchSettings, ModelSettings
from ingenious.services.azure_search.builders import (
    ConfigError,
    _pick_models,
    build_search_config_from_settings,
)

if TYPE_CHECKING:
    from pytest import LogCaptureFixture, MonkeyPatch


def _settings(
    models: list[ModelSettings] | None, azure: AzureSearchSettings | None
) -> IngeniousSettings:
    """Construct a minimal IngeniousSettings object for testing.

    This helper function simplifies test setup by creating a settings object
    with only the model and Azure Search service configurations populated.
    """
    s = IngeniousSettings.model_construct()
    s.models = models
    s.azure_search_services = [azure] if azure else None
    return s


def test_build_search_config_maps_and_validates(monkeypatch: MonkeyPatch) -> None:
    """Verify settings are correctly mapped to SearchConfig on the happy path.

    This test ensures that when valid settings for both models and Azure Search
    are provided, they are correctly translated into the `SearchConfig` data
    structure used by the search service client.
    """
    models: list[ModelSettings] = [
        ModelSettings(
            model="text-embedding-3-small",
            deployment="embed",
            api_key="K1",
            base_url="https://oai",
            api_version="2024-02-01",
        ),
        ModelSettings(
            model="gpt-5",
            deployment="chat",
            api_key="K2",
            base_url="https://oai",
            api_version="2024-02-01",
        ),
    ]
    azure = AzureSearchSettings(
        service="svc",
        endpoint="https://search.windows.net",
        key="SKEY",
        index_name="idx",
    )
    cfg = build_search_config_from_settings(_settings(models, azure))
    assert cfg.search_endpoint == "https://search.windows.net"
    assert cfg.search_index_name == "idx"
    assert cfg.embedding_deployment_name == "embed"
    assert cfg.generation_deployment_name == "chat"
    assert cfg.openai_endpoint == "https://oai"
    assert cfg.openai_key.get_secret_value() in {
        "K2",
        "K1",
    }  # chosen from gen then emb


def test_build_search_config_errors() -> None:
    """Verify that ConfigError is raised for missing or invalid settings.

    This test confirms that the configuration builder performs essential
    validation, raising an error if the Azure Search service block is missing
    or if critical fields like endpoint, key, or index name are empty.
    """
    models: list[ModelSettings] = [
        ModelSettings(model="gpt-5", deployment="chat", api_key="k", base_url="https://o")
    ]
    with pytest.raises(ConfigError):
        build_search_config_from_settings(_settings(models, None))

    azure = AzureSearchSettings(service="svc", endpoint="", key="", index_name="")
    with pytest.raises(ConfigError):
        build_search_config_from_settings(_settings(models, azure))

    azure2 = AzureSearchSettings(service="svc", endpoint="https://s", key="k", index_name="")
    with pytest.raises(ConfigError):
        build_search_config_from_settings(_settings(models, azure2))


def test_pick_models_selection_and_require_deployments(
    caplog: LogCaptureFixture,
) -> None:
    """Test model selection logic, deployment requirements, and warnings.

    This test case validates the behavior of the `_pick_models` helper. It ensures
    that the function raises a `ConfigError` if a model is missing a required
    deployment name and that it logs a warning if a single model is being
    reused for both embedding and generation roles.
    """
    caplog.set_level(logging.WARNING)
    models: list[ModelSettings] = [
        ModelSettings(
            model="text-embedding-3-small",
            deployment="emb",
            api_key="k",
            base_url="https://o",
        ),
    ]
    # It should fail if a model is found for a role but lacks a deployment name.
    with pytest.raises(ConfigError):
        _pick_models(
            _settings(
                [ModelSettings(model="gpt-5", deployment="", api_key="k", base_url="https://o")],
                AzureSearchSettings(service="s", endpoint="https://e", key="k", index_name="i"),
            )
        )
    # Single model with a deployment name should be selected for both roles,
    # but it should trigger a warning.
    _ = _pick_models(
        _settings(
            models,
            AzureSearchSettings(service="s", endpoint="https://e", key="k", index_name="i"),
        )
    )
    assert any("Single ModelSettings provided" in rec.message for rec in caplog.records)
