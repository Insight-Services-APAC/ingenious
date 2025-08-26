# ingenious/client/azure/builder/search_client_async.py
from __future__ import annotations

import inspect
from typing import Any, Mapping, Optional, Union

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.aio import SearchClient as AsyncSearchClient

try:
    # Precise async token protocol for typing
    from azure.core.credentials_async import AsyncTokenCredential
except Exception:  # pragma: no cover - typing fallback if azure-core version differs

    class AsyncTokenCredential:  # type: ignore[no-redef]
        async def get_token(self, *scopes: str) -> Any:  # pragma: no cover - typing aid
            ...


def _get(obj: Any, *names: str) -> Any:
    """Return first non-empty attribute / mapping value by any of the given names."""
    for n in names:
        if isinstance(obj, Mapping):
            if n in obj and obj[n] not in (None, ""):
                return obj[n]
        else:
            v = getattr(obj, n, None)
            if v not in (None, ""):
                return v
    return None


def _to_plain_secret(value: Any) -> Optional[str]:
    """Unwrap pydantic SecretStr or return the string directly."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    getter = getattr(value, "get_secret_value", None)
    if callable(getter):
        try:
            return getter()
        except Exception:
            return None
    return None


def _filter_kwargs_for_ctor(cls: type, kwargs: dict[str, Any]) -> dict[str, Any]:
    """
    Only pass kwargs the constructor actually accepts.

    - If the __init__ has **kwargs, keep everything.
    - Otherwise, drop unknown keys to avoid TypeError with strict fakes or SDK changes.
    """
    try:
        sig = inspect.signature(cls.__init__)
    except (ValueError, TypeError):
        # If signature introspection fails, pass as-is (best effort).
        return kwargs

    params = sig.parameters.values()
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params):
        return kwargs  # ctor accepts **kwargs, no filtering necessary

    allowed = {
        p.name
        for p in params
        if p.kind
        in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    # 'self' will never be in kwargs; no need to remove it explicitly
    return {k: v for k, v in kwargs.items() if k in allowed}


class AzureSearchAsyncClientBuilder:
    """
    Builder for `azure.search.documents.aio.SearchClient`.

    Prefers async AAD token credentials (from `azure.identity.aio`) when available.
    Falls back to `AzureKeyCredential` when only a key is provided, and finally to
    `DefaultAzureCredential` if neither explicit token nor key is provided.

    Any additional keyword arguments provided via `client_options` are forwarded
    to the underlying SDK constructor. This builder does not attempt to normalize
    or alias option names; callers should use azure-core/azure-search supported
    kwargs (e.g., retry or transport settings).
    """

    def __init__(
        self,
        *,
        endpoint: str,
        index_name: str,
        credential: Union[AsyncTokenCredential, AzureKeyCredential],
        **client_options: Any,
    ) -> None:
        self._endpoint = endpoint
        self._index_name = index_name
        self._credential = credential
        self._client_options: dict[str, Any] = dict(client_options or {})

    @classmethod
    def from_config(
        cls,
        config: Optional[Mapping[str, Any] | Any],
        *,
        index_name: str,
        client_options: Optional[Mapping[str, Any]] = None,
    ) -> "AzureSearchAsyncClientBuilder":
        """
        Resolve endpoint and credentials from a flexible config mapping/object.

        Recognized fields:
        - endpoint (preferred), search_endpoint, base_url, or service -> service URL
        - Prefer AAD token if any of:
            * tenant_id + client_id + client_secret  (ClientSecretCredential)
            * managed_identity_client_id              (ManagedIdentityCredential)
            * explicit preference via prefer_token / use_token truthy flag
        - Key aliases: search_key, key, api_key      -> AzureKeyCredential
        """
        cfg = config or {}

        # ---- Endpoint resolution (add 'service' fallback for parity with sync) ----
        endpoint = _get(cfg, "endpoint", "search_endpoint", "base_url")
        if not endpoint:
            service = _get(cfg, "service")
            if service:
                endpoint = f"https://{service}.search.windows.net"

        if not endpoint:
            raise ValueError(
                "Azure Search endpoint is required (use 'endpoint' or 'search_endpoint', "
                "or provide 'service' to derive it)."
            )

        # ---- (unchanged) credential resolution below ----
        tenant_id = _get(cfg, "tenant_id")
        client_id = _get(cfg, "client_id")
        client_secret = _to_plain_secret(_get(cfg, "client_secret"))
        msi_client_id = _get(cfg, "managed_identity_client_id")
        key = _to_plain_secret(_get(cfg, "search_key", "key", "api_key"))
        prefer_token_flag = bool(_get(cfg, "prefer_token", "use_token") or False)

        cred: Union[AsyncTokenCredential, AzureKeyCredential, None] = None
        if tenant_id and client_id and client_secret:
            from azure.identity.aio import ClientSecretCredential

            cred = ClientSecretCredential(
                tenant_id=str(tenant_id),
                client_id=str(client_id),
                client_secret=str(client_secret),
            )
        elif msi_client_id:
            from azure.identity.aio import ManagedIdentityCredential

            cred = ManagedIdentityCredential(client_id=str(msi_client_id))
        elif prefer_token_flag or not key:
            try:
                from azure.identity.aio import DefaultAzureCredential
            except Exception as e:  # pragma: no cover
                if not key:
                    raise ImportError(
                        "azure-identity is required for token auth or provide 'search_key'."
                    ) from e
            else:
                cred = DefaultAzureCredential(
                    exclude_interactive_browser_credential=True
                )

        if cred is None and key:
            cred = AzureKeyCredential(str(key))

        if cred is None:
            from azure.identity.aio import DefaultAzureCredential

            cred = DefaultAzureCredential(exclude_interactive_browser_credential=True)

        return cls(
            endpoint=str(endpoint),
            index_name=index_name,
            credential=cred,
            **dict(client_options or {}),
        )

    def build(self) -> AsyncSearchClient:
        # Defensive: drop unknown kwargs if constructor doesn't accept **kwargs.
        filtered_opts = _filter_kwargs_for_ctor(AsyncSearchClient, self._client_options)
        return AsyncSearchClient(
            endpoint=self._endpoint,
            index_name=self._index_name,
            credential=self._credential,
            **filtered_opts,
        )
