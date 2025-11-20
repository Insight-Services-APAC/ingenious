# -- coding: utf-8 --
"""Validate the Azure Search configuration model.

This test module ensures that the `SearchConfig` Pydantic model behaves as
expected. It validates required fields, confirms the application of default
values, and verifies the model's immutability (`frozen=True`). These tests
guarantee that the configuration used by the search service is always valid
and prevents accidental modification at runtime. A basic sanity check of the
default prompt content is also included.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from ingenious.services.azure_search.config import DEFAULT_DAT_PROMPT, SearchConfig


def test_search_config_valid(config: SearchConfig) -> None:
    """Validate a properly configured SearchConfig instance.

    This test ensures that when a valid configuration is provided, all fields
    are correctly parsed and have the expected formats or values.
    """
    assert config.search_endpoint.startswith("https://")
    assert config.openai_endpoint.startswith("https://")
    assert isinstance(config.search_key, SecretStr)
    assert isinstance(config.openai_key, SecretStr)
    assert config.embedding_deployment_name
    assert config.generation_deployment_name
    assert config.openai_version == "2024-02-01"
    assert config.use_semantic_ranking is True


def test_search_config_missing_required_fields() -> None:
    """Verify ValidationError is raised for missing required fields.

    This test ensures the model's validation enforces the presence of essential
    configuration like API endpoints and keys, which are critical for operation.
    """
    data: dict[str, Any] = dict(
        search_endpoint="http://localhost",
        search_key=SecretStr("x"),
        search_index_name="idx",
    )
    with pytest.raises(ValidationError) as e:
        SearchConfig(**data)
    locs: set[tuple[str, ...]] = {tuple(err["loc"]) for err in e.value.errors()}
    assert ("openai_endpoint",) in locs
    assert ("openai_key",) in locs
    assert ("embedding_deployment_name",) in locs
    assert ("generation_deployment_name",) in locs


def test_search_config_defaults_minimal_ok() -> None:
    """Confirm default values are applied for optional fields.

    This test checks that when a user provides only the required fields, the
    model correctly populates sensible defaults for optional settings like
    retrieval counts and field names.
    """
    cfg: SearchConfig = SearchConfig(
        search_endpoint="http://s",
        search_key=SecretStr("a"),
        search_index_name="i",
        openai_endpoint="http://o",
        openai_key=SecretStr("b"),
        embedding_deployment_name="e",
        generation_deployment_name="g",
    )
    assert cfg.top_k_retrieval == 20
    assert cfg.top_n_final == 5
    assert cfg.id_field == "id"
    assert cfg.content_field == "content"
    assert cfg.vector_field == "vector"
    assert cfg.dat_prompt == DEFAULT_DAT_PROMPT
    assert cfg.semantic_configuration_name is None


def test_search_config_is_frozen(config: SearchConfig) -> None:
    """Ensure the SearchConfig model is immutable.

    This test verifies that the `frozen=True` Pydantic setting correctly
    prevents attribute modification after instantiation, which helps avoid
    unexpected state changes during the application's lifecycle.
    """
    with pytest.raises(ValidationError):
        config.top_k_retrieval = 99  # type: ignore[misc]


def test_default_dat_prompt_has_key_sections() -> None:
    """Sanity-check the content of the default DAT prompt.

    This test performs a basic check to ensure the default prompt string
    contains key instructional phrases, guarding against accidental regressions
    or malformed prompt content.
    """
    s: str = DEFAULT_DAT_PROMPT
    assert "System:" in s
    assert "Scoring Criteria" in s
    assert "Direct Hit -> 5 points" in s
    assert "Completely Off-Track -> 0 points" in s
    assert "Respond ONLY with two integers" in s
