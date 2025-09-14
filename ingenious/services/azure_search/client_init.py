"""Create Azure AI service clients via the central factory (async).

This module provides the single seam the codebase and tests patch to inject
Azure clients. It deliberately keeps import-time light and avoids pulling the
real SDKs unless a call site actually asks for a client.

Why/what:
- Prefer a module-level `AzureClientFactory` symbol when set (tests patch this).
- Otherwise, lazily import the production factory
  `ingenious.client.azure.AzureClientFactory`.
- Normalize OpenAI client options (notably retries) with validation and safe
  defaults, while dropping unknown kwargs to keep the surface stable.

Key entry points (public API):
- `make_async_search_client(cfg, **client_options)`
- `make_async_openai_client(cfg, **client_options)`

I/O/Deps/Side effects:
- Depends on `ingenious.client.azure.AzureClientFactory` at runtime unless tests
  patch `AzureClientFactory` here.
- Unwraps `SecretStr` secrets at the call boundary to avoid leaking across layers.

Usage:
    search = make_async_search_client(cfg, retry_total=4)
    openai = make_async_openai_client(cfg, max_retries=5, timeout=20.0)
    ...
    await search.close()
    await openai.close()
"""
# Insight_Ingenious/ingenious/services/azure_search/client_init.py
from __future__ import annotations

import logging
from importlib import import_module
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from azure.search.documents.aio import SearchClient
    from openai import AsyncAzureOpenAI

    from .config import SearchConfig

# ─────────────────────────────────────────────────────────────────────────────
# Patch seam: tests set this to a dummy factory class with the same API.
# If left as None, we import the production factory on demand.
# ─────────────────────────────────────────────────────────────────────────────
AzureClientFactory: Any | None = None  # patched by tests

__all__ = ["make_async_search_client", "make_async_openai_client"]

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
LOGGER_NAME = "ingenious.services.azure_search.client_init"
DEFAULT_OPENAI_MAX_RETRIES = 3
ALLOWED_OPENAI_OPTION_KEYS: set[str] = {
    "max_retries",
    "timeout",
    "connect_timeout",
    "read_timeout",
    "transport",
    "http_client",
}

log = logging.getLogger(LOGGER_NAME)


def _get_factory() -> Any:
    """Resolve and return the Azure client factory class.

    Uses the patched `AzureClientFactory` when provided by tests; otherwise,
    lazily imports the production factory to minimize import-time overhead.

    Returns:
        The factory class used to create concrete Azure clients.
    """
    if AzureClientFactory is not None:
        log.debug("Using patched AzureClientFactory: %s", AzureClientFactory)
        return AzureClientFactory

    module = import_module("ingenious.client.azure")
    _F = getattr(module, "AzureClientFactory")
    log.debug("Using production AzureClientFactory: %s", _F)
    return _F


def _normalize_openai_options(client_options: dict[str, Any]) -> dict[str, Any]:
    """Normalize and validate options forwarded to the OpenAI client factory.

    Behavior/contract (mirrors test expectations):
    - Accept alias `retries` and map to `max_retries`.
    - Apply a sane default of `max_retries=3` when not provided.
    - Reject negative retry counts with `ValueError`.
    - Drop unknown kwargs silently (keep surface stable).

    Args:
        client_options: Arbitrary keyword options supplied by callers.

    Returns:
        A sanitized dict containing only supported keys with validated values.

    Raises:
        ValueError: If `max_retries`/`retries` specifies a negative value.
        ValueError: If a non-integer value is provided for retries.
    """
    out: dict[str, Any] = {}

    # Normalize retries (support alias and default).
    raw_max = client_options.get("max_retries", client_options.get("retries", None))
    if raw_max is None:
        max_retries: int = DEFAULT_OPENAI_MAX_RETRIES
    else:
        max_retries = int(raw_max)  # may raise ValueError; let it bubble
    if max_retries < 0:
        raise ValueError("max_retries must be >= 0")
    out["max_retries"] = max_retries

    # Copy only allowed remaining options.
    for k in ALLOWED_OPENAI_OPTION_KEYS:
        if k == "max_retries":
            continue
        if k in client_options:
            out[k] = client_options[k]

    return out


def make_async_search_client(
    cfg: "SearchConfig", **client_options: Any
) -> "SearchClient":
    """Create the async Azure Search client via the selected factory.

    Any keyword args in `client_options` are forwarded verbatim to the underlying
    SDK constructor through the factory. The Azure Search SDK usually validates
    these.

    Args:
        cfg: Validated `SearchConfig`.
        **client_options: Optional Azure SDK configuration (timeouts, retries,
            etc.).

    Returns:
        An instance of the async `SearchClient`.
    """
    factory = _get_factory()
    return cast(
        "SearchClient",
        factory.create_async_search_client(
            index_name=cfg.search_index_name,
            config={
                "endpoint": cfg.search_endpoint,
                "search_key": cfg.search_key.get_secret_value(),  # unwrap SecretStr
            },
            **client_options,
        ),
    )


def make_async_openai_client(
    cfg: "SearchConfig", **client_options: Any
) -> "AsyncAzureOpenAI":
    """Create the async Azure OpenAI client via the selected factory.

    Behavior:
    - Applies a sane default retry policy (`max_retries=3`) unless overridden.
    - Accepts alias `retries` and maps it to `max_retries`.
    - Drops unknown kwargs to keep a stable factory/SDK surface.
    - Validates that retries are non-negative.

    Args:
        cfg: Validated `SearchConfig`.
        **client_options: Optional OpenAI client options. Supported keys include:
            - max_retries (int), retries (alias), timeout (float),
              connect_timeout (float), read_timeout (float),
              transport/http_client.

    Returns:
        An instance of `AsyncAzureOpenAI`.

    Raises:
        ValueError: If a negative retry count is provided or parsing fails.
    """
    factory = _get_factory()
    normalized: dict[str, Any] = _normalize_openai_options(dict(client_options))

    return cast(
        "AsyncAzureOpenAI",
        factory.create_async_openai_client(
            config={
                "openai_endpoint": cfg.openai_endpoint,
                "openai_key": cfg.openai_key.get_secret_value(),  # unwrap SecretStr
            },
            api_version=cfg.openai_version,
            **normalized,
        ),
    )
