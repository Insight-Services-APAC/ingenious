"""Verifies validation for Azure Search numeric configuration knobs.

This module contains tests to ensure that critical numeric settings for the
Azure Search service, such as 'top_k_retrieval' and 'top_n_final', are
properly validated. The primary goal is to prevent non-positive integer
values from being accepted, as they would lead to invalid search queries.

The tests are designed to be flexible and will pass whether the validation
logic is implemented in the `build_search_config_from_settings` builder
function (preferred) or directly within the `SearchConfig` Pydantic model.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pytest import MonkeyPatch


try:
    # Prefer validating through the builder (recommended change).
    import ingenious.services.azure_search.builders as builders
    from ingenious.services.azure_search.builders import (
        build_search_config_from_settings as build_cfg,
    )

    USING_BUILDER: bool = True
except ImportError:  # pragma: no cover - fall back to model-level validation if needed
    USING_BUILDER = False

# Fallback: if you instead add constrained ints on the model, this path will cover it.
if not USING_BUILDER:
    # Adjust this import if your config model lives elsewhere:
    from ingenious.services.azure_search.config import (
        SearchConfig,
    )


@pytest.mark.parametrize(
    "top_k_retrieval, top_n_final",
    [
        (0, 10),  # top_k == 0
        (-1, 10),  # top_k < 0
        (10, 0),  # top_n == 0
        (10, -5),  # top_n < 0
        (0, 0),  # both invalid
    ],
)
def test_builder_rejects_non_positive_topk_topn(
    monkeypatch: MonkeyPatch, top_k_retrieval: int, top_n_final: int
) -> None:
    """Reject non-positive values for top_k_retrieval and top_n_final.

    This test ensures that the configuration loading process raises an exception
    if `top_k_retrieval` or `top_n_final` are zero or negative. This is a
    critical defensive check to prevent invalid search queries.

    The test is structured to adapt to two possible validation strategies:
      - A `ValueError` raised from the `build_search_config_from_settings` builder.
      - A `pydantic.ValidationError` raised from the `SearchConfig` model itself.
    """
    if USING_BUILDER:
        # Build a minimal settings stub for the builder.
        # NOTE: Adjust attribute names if your builder expects different ones.

        # Minimal Azure Search service stanza the builder reads from settings.azure_search_services[0]
        service: SimpleNamespace = SimpleNamespace(
            endpoint="https://example.search.windows.net",
            api_key="test-key",
            index_name="test-index",
            use_semantic_ranking=False,
            semantic_configuration_name=None,
            # Add the top_k and top_n values here for the test
            top_k_retrieval=top_k_retrieval,
            top_n_final=top_n_final,
        )

        # Provide settings with the service
        settings: SimpleNamespace = SimpleNamespace(
            azure_search_services=[service],
        )

        # Mock _pick_models to return a tuple of 5 values as expected
        def mock_pick_models(
            _settings: Any,
        ) -> tuple[str, str, str, str, str]:
            """Provide dummy model configuration to satisfy the builder."""
            return (
                "https://aoai.local",  # openai_endpoint
                "sk-test",  # openai_key
                "2024-05-01-preview",  # openai_version
                "embedding-deploy",  # embedding_deployment
                "chat-deploy",  # generation_deployment
            )

        monkeypatch.setattr(builders, "_pick_models", mock_pick_models)

        with pytest.raises(ValueError):
            build_cfg(settings)

    else:
        # Model-level validation path (if you chose to enforce via constrained ints on SearchConfig)
        from pydantic import ValidationError

        # NOTE: Adjust required fields according to your SearchConfig definition.
        with pytest.raises(ValidationError):
            SearchConfig(
                # Azure Search bits
                search_endpoint="https://example.search.windows.net",
                search_api_key="test-key",
                index_name="test-index",
                # AOAI bits (if your model carries them)
                openai_endpoint="https://aoai.local",
                openai_api_key="sk-test",
                openai_api_version="2024-05-01-preview",
                embedding_deployment="embedding-deploy",
                chat_deployment="chat-deploy",
                # Knobs under test
                top_k_retrieval=top_k_retrieval,
                top_n_final=top_n_final,
            )
