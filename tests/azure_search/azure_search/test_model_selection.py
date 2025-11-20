"""Test model selection logic for Azure Search configuration builders.

This module verifies that the configuration builder functions correctly validate
and select Azure OpenAI models for chat and embedding roles. It ensures that
common misconfigurations, such as missing deployment names or conflicting
deployment assignments, are caught early and raise appropriate errors.

The primary function under test is `build_search_config_from_settings`.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

# ⬇️ ADJUST THESE IMPORTS to match where your builders live
from ingenious.services.azure_search.builders import (
    ConfigError,
    _pick_models,
    build_search_config_from_settings,
)


def _settings(**overrides: Any) -> SimpleNamespace:
    """Create a mock settings object for builder tests.

    This helper mimics the shape of the configuration object that the builder
    functions expect, allowing for isolated testing of model selection logic.
    If your project already exposes a fixture/helper, prefer that instead.
    """
    # Minimal model items: provider, role, deployment, endpoint/key, api_version
    models: list[SimpleNamespace] = overrides.pop(
        "models",
        [
            # Chat model with deployment
            SimpleNamespace(
                provider="azure_openai",
                role="chat",
                endpoint="https://aoai.example.com",
                key="x",
                api_version="2024-02-15-preview",
                deployment="gpt-5",
                model="gpt-5",
            ),
            # Embedding model WITHOUT deployment (this is the case we want to fail)
            SimpleNamespace(
                provider="azure_openai",
                role="embedding",
                endpoint="https://aoai.example.com",
                key="x",
                api_version="2024-02-15-preview",
                deployment="",  # ❌ missing
                model="text-embedding-3-large",
            ),
        ],
    )

    # Minimal azure search service entry
    azure_search_services: list[SimpleNamespace] = overrides.pop(
        "azure_search_services",
        [
            SimpleNamespace(
                endpoint="https://acct.search.windows.net",
                key="x",
                index_name="idx",
                semantic_ranking=True,
                semantic_configuration="my-semantic",
            )
        ],
    )

    return SimpleNamespace(models=models, azure_search_services=azure_search_services, **overrides)


def test_pick_models_requires_embedding_deployment() -> None:
    """Verify `_pick_models` raises an error if an embedding model lacks a deployment.

    This test ensures that the model selection logic enforces a critical
    precondition: an Azure OpenAI embedding model must have a non-empty
    deployment name to be usable by the search service.
    """
    s: SimpleNamespace = _settings()
    with pytest.raises(ValueError):  # The builders typically raise ValueError for selection faults
        _pick_models(s)


@pytest.mark.parametrize(
    "embed_dep, chat_dep, should_raise",
    [
        ("emb-001", "gpt-5", False),  # different deployments — OK
        (
            "shared-dep",
            "shared-dep",
            True,
        ),  # same deployments — should raise if guard is enabled
    ],
)
def test_builder_rejects_same_deployments_for_embed_and_chat(
    embed_dep: str, chat_dep: str, should_raise: bool
) -> None:
    """Verify builder rejects configs where chat and embedding models share a deployment.

    This test enforces a policy that the chat and embedding models must use
    distinct deployments. This prevents potential API conflicts or billing
    ambiguity where a single endpoint serves multiple model types.
    """
    s: SimpleNamespace = _settings(
        models=[
            SimpleNamespace(
                provider="azure_openai",
                role="embedding",
                endpoint="https://aoai.example.com",
                key="x",
                api_version="2024-02-15-preview",
                deployment=embed_dep,
                model="text-embedding-3-large",
            ),
            SimpleNamespace(
                provider="azure_openai",
                role="chat",
                endpoint="https://aoai.example.com",
                key="x",
                api_version="2024-02-15-preview",
                deployment=chat_dep,
                model="gpt-5",
            ),
        ]
    )

    if should_raise:
        with pytest.raises(ConfigError):
            build_search_config_from_settings(s)
    else:
        cfg: Any = build_search_config_from_settings(s)
        # Sanity: the builder still returns a config object if deployments differ
        assert hasattr(cfg, "openai"), "Expected a SearchConfig-like object with .openai fields"
