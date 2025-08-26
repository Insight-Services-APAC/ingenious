"""Tests the model selection logic for Azure Search builders.

This module contains unit tests for the `_pick_models` helper function, which is
responsible for selecting appropriate embedding and generation models from the
application settings. The tests ensure that the selection process is
deterministic and that it correctly raises configuration errors when no
suitable models are found. This is critical for guaranteeing predictable
Azure Search client setup.
"""

from __future__ import annotations

from typing import Any

import pytest

from ingenious.config.main_settings import IngeniousSettings
from ingenious.config.models import AzureSearchSettings, ModelSettings
from ingenious.services.azure_search.builders import ConfigError, _pick_models


def _settings(
    models: list[ModelSettings], azure: AzureSearchSettings | None = None
) -> IngeniousSettings:
    """Construct a minimal IngeniousSettings object for testing.

    This helper function simplifies the creation of settings objects needed
    by the tests, isolating the model and Azure Search service configurations.

    Args:
        models: A list of model settings to include.
        azure: An optional Azure Search service configuration.

    Returns:
        A partially constructed IngeniousSettings instance.
    """
    s = IngeniousSettings.model_construct()
    s.models = models
    s.azure_search_services = [azure] if azure else []
    return s


def test_pick_models_first_match_deterministic() -> None:
    """Verify _pick_models deterministically selects the first valid models.

    This test ensures that when multiple suitable embedding and generation
    models are available, the function consistently chooses the first one of
    each type listed in the configuration. This guarantees predictable
    behavior.
    """
    models: list[ModelSettings] = [
        ModelSettings(
            model="text-embedding-3-small",
            deployment="emb-1",
            api_key="K",
            base_url="https://oai",
            api_version="2024-02-01",
        ),
        ModelSettings(
            model="text-embedding-3-large",
            deployment="emb-2",
            api_key="K",
            base_url="https://oai",
            api_version="2024-02-01",
        ),
        ModelSettings(
            model="gpt-4o",
            deployment="chat-1",
            api_key="K",
            base_url="https://oai",
            api_version="2024-02-01",
        ),
        ModelSettings(
            model="gpt-35-turbo",
            deployment="chat-2",
            api_key="K",
            base_url="https://oai",
            api_version="2024-02-01",
        ),
    ]
    azure = AzureSearchSettings(
        service="svc", endpoint="https://s", key="sk", index_name="idx"
    )

    picked: Any = _pick_models(_settings(models, azure))

    emb_dep: str | None
    gen_dep: str | None
    # Accept either tuple or object return shapes
    if isinstance(picked, tuple):
        # Mypy cannot handle unpacking a tuple of unknown size from `Any`.
        *_, emb_dep, gen_dep = picked
    else:
        emb_dep = getattr(picked, "embedding_deployment", None)
        gen_dep = getattr(picked, "generation_deployment", None)

    assert emb_dep == "emb-1"  # first embedding wins
    assert gen_dep == "chat-1"  # first GPT/4o-ish wins


def test_pick_models_requires_any_valid_candidates() -> None:
    """Verify _pick_models raises ConfigError if no suitable models are found.

    This test confirms that the application will fail to start with a clear
    error if the configuration lacks any models that can be used for
    embedding or text generation, preventing runtime errors later.
    """
    models: list[ModelSettings] = [
        ModelSettings(
            model="other-model",
            deployment="other",
            api_key="K",
            base_url="https://oai",
            api_version="2024-02-01",
        )
    ]
    azure = AzureSearchSettings(
        service="svc", endpoint="https://s", key="sk", index_name="idx"
    )
    with pytest.raises(ConfigError):
        _pick_models(_settings(models, azure))
