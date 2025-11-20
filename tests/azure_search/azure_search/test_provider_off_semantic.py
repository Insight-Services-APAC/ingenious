# -*- coding: utf-8 -*-
"""When semantic ranking is OFF, provider delegates to pipeline which uses fused scores."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from ingenious.config.main_settings import IngeniousSettings
from ingenious.config.models import AzureSearchSettings, ModelSettings
from ingenious.services.azure_search.provider import AzureSearchProvider


def _make_settings_off_semantic() -> IngeniousSettings:
    s = IngeniousSettings.model_construct()
    s.models = [
        ModelSettings(
            model="text-embedding-3-small",
            deployment="emb",
            api_key="K",
            base_url="https://oai.example.com",
            api_version="2024-02-01",
        ),
        ModelSettings(
            model="gpt-5",
            deployment="chat",
            api_key="K",
            base_url="https://oai.example.com",
            api_version="2024-02-01",
        ),
    ]
    s.azure_search_services = [
        AzureSearchSettings(
            service="svc",
            endpoint="https://search.example.net",
            key="SK",
            index_name="idx",
            use_semantic_ranking=False,
        )
    ]
    return s


@pytest.mark.asyncio
async def test_provider_retrieve_without_semantic_uses_fused_scores_and_top_k(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test provider retrieval without semantic ranking uses fused scores.

    Verifies that when semantic ranking is disabled, the provider delegates
    to the pipeline which returns results with fused scores and respects top_k.
    """
    settings: IngeniousSettings = _make_settings_off_semantic()

    pipeline = MagicMock()
    fused: list[dict[str, Any]] = [
        {"id": "A", "content": "A"},
        {"id": "B", "content": "B"},
        {"id": "C", "content": "C"},
    ]
    pipeline.retrieve = AsyncMock(return_value=fused[:2])  # top_k=2

    monkeypatch.setattr(
        "ingenious.services.azure_search.provider.build_search_pipeline",
        lambda _cfg: pipeline,
        raising=False,
    )

    provider = AzureSearchProvider(settings)
    out = await provider.retrieve("q", top_k=2)
    assert len(out) == 2
    await provider.close()
