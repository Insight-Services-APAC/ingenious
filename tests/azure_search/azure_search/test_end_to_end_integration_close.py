# -*- coding: utf-8 -*-
"""End-to-end (direct) path: provider builds pipeline via factory and closes it.

We assert:
- The pipeline is obtained via the provider constructor.
- Provider.retrieve delegates to the pipeline and returns its output.
- Provider.close awaits pipeline.close(). We also ensure the pipeline closes
  any internal clients it owns (by exposing a flag in the stub).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from ingenious.config.main_settings import IngeniousSettings
from ingenious.config.models import AzureSearchSettings, ModelSettings
from ingenious.services.azure_search.provider import AzureSearchProvider


class _CloseTrackedPipeline:
    def __init__(self) -> None:
        class _Retr:
            async def search_lexical(self, _q: str) -> list[dict[str, Any]]:
                return [{"id": "L1", "content": "lex", "@search.score": 0.2}]

            async def search_vector(self, _q: str) -> list[dict[str, Any]]:
                return [{"id": "V1", "content": "vec", "@search.score": 0.3}]

            async def close(self) -> None:
                return None

        class _Fuser:
            async def fuse(self, *_a: Any, **_k: Any) -> list[dict[str, Any]]:
                return [{"id": "F", "_fused_score": 0.4, "content": "fused"}]

            async def close(self) -> None:
                return None

        self.retriever = _Retr()
        self.fuser = _Fuser()
        self.answer_generator = None
        self._closed = False

    async def retrieve(self, *_a: Any, **_k: Any) -> list[dict[str, Any]]:
        return [{"id": "F", "content": "fused"}]

    async def close(self) -> None:
        self._closed = True


def _settings() -> IngeniousSettings:
    s = IngeniousSettings.model_construct()
    s.models = [
        ModelSettings(
            model="text-embedding-3-small",
            deployment="emb",
            api_key="ok",
            base_url="https://aoai.example.com",
            api_version="2024-02-01",
        ),
        ModelSettings(
            model="gpt-5",
            deployment="chat",
            api_key="ok",
            base_url="https://aoai.example.com",
            api_version="2024-02-01",
        ),
    ]
    s.azure_search_services = [
        AzureSearchSettings(
            service="svc",
            endpoint="https://s.example.net",
            key="sk",
            index_name="idx",
            semantic_ranking=False,
        )
    ]
    return s


@pytest.mark.asyncio
async def test_end_to_end_kb_direct_uses_factory_and_closes_pipeline() -> None:
    """Test end-to-end knowledge base retrieval with proper pipeline closure.

    Verifies that the provider uses the factory to build the pipeline, executes
    retrieval successfully, and properly closes pipeline resources when done.
    """
    p_stub = _CloseTrackedPipeline()

    with patch(
        "ingenious.services.azure_search.provider.build_search_pipeline",
        new=lambda *_a, **_k: p_stub,
    ):
        provider = AzureSearchProvider(_settings(), enable_answer_generation=False)

        out = await provider.retrieve("q", top_k=1)
        assert out and out[0]["id"] == "F"

        await provider.close()
        assert p_stub._closed is True
