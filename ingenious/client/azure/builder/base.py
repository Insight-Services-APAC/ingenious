"""
Azure client builder base class with lazy AAD imports.

Why:
- Keep import-time light by avoiding hard dependencies on `azure-identity`
  unless a caller actually selects an AAD-based authentication method.
- Centralize credential resolution (AAD token vs API key) for all concrete
  builders and provide helper properties for common needs.

Usage:
    builder = SomeConcreteBuilder.from_config(cfg)
    client = builder.build()

Key entry points:
- AzureClientBuilder.credential (lazy AAD import + caching)
- AzureClientBuilder.api_key / key_credential / token_credential
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional, Union

# AzureKeyCredential is lightweight; still guard it to be safe
try:
    from azure.core.credentials import (
        AzureKeyCredential,
    )
except Exception:  # pragma: no cover - fallback for environments w/o azure-core

    class AzureKeyCredential:
        def __init__(self, key: str) -> None:
            self.key = key


# TokenCredential / identity types: type-only to avoid hard dependency at import time
if TYPE_CHECKING:
    from azure.core.credentials import TokenCredential

    # Identity types are imported only for static typing; runtime imports are lazy.
else:
    # Runtime sentinel so attribute access is explicit and predictable
    class _TokenCredentialSentinel:  # pragma: no cover
        """Sentinel for TokenCredential type when azure-core is unavailable at import time."""

        pass

    TokenCredential = _TokenCredentialSentinel  # type: ignore[misc, assignment]
    # Identity classes are imported lazily inside methods at runtime.

from ingenious.common.enums import AuthenticationMethod
from ingenious.config.auth_config import AzureAuthConfig


class AzureClientBuilder(ABC):
    """Abstract base class for Azure client builders with authentication support."""

    def __init__(self, auth_config: Optional[AzureAuthConfig] = None) -> None:
        """Initialize builder with optional pre-parsed auth configuration."""
        self.auth_config = auth_config or AzureAuthConfig.default_credential()
        self._credential: Any | None = None  # Lazy-loaded credential cache

    @classmethod
    def from_config(cls, config: Any) -> "AzureClientBuilder":
        """
        Create builder instance from a configuration object.

        Args:
            config: Configuration object (either legacy or new format)

        Returns:
            Builder instance with authentication configuration extracted.
        """
        auth_config = AzureAuthConfig.from_config(config)
        return cls(auth_config=auth_config)

    @property
    def credential(self) -> Union[TokenCredential, AzureKeyCredential]:
        """
        Get the appropriate credential based on authentication method.
        Cached after first access for efficiency.

        Returns:
            TokenCredential: For Azure AD authentication
                (DEFAULT_CREDENTIAL, MSI, CLIENT_ID_AND_SECRET).
            AzureKeyCredential: For API key authentication (TOKEN).
        """
        if self._credential is None:
            # Validate authentication configuration
            self.auth_config.validate_for_method()

            # Lazy runtime import of identity classes only when needed.
            def _import_identity():
                try:
                    from azure.identity import (
                        ClientSecretCredential,
                        DefaultAzureCredential,
                        ManagedIdentityCredential,
                    )

                    return (
                        DefaultAzureCredential,
                        ManagedIdentityCredential,
                        ClientSecretCredential,
                    )
                except Exception as e:  # pragma: no cover
                    raise ImportError(
                        "azure-identity is required for AAD authentication. "
                        "Install with: pip install azure-identity"
                    ) from e

            if (
                self.auth_config.authentication_method
                == AuthenticationMethod.DEFAULT_CREDENTIAL
            ):
                (
                    DefaultAzureCredential,
                    ManagedIdentityCredential,
                    ClientSecretCredential,
                ) = _import_identity()
                self._credential = DefaultAzureCredential()

            elif self.auth_config.authentication_method == AuthenticationMethod.MSI:
                (
                    DefaultAzureCredential,
                    ManagedIdentityCredential,
                    ClientSecretCredential,
                ) = _import_identity()
                if not self.auth_config.client_id:
                    # Use system-assigned managed identity
                    self._credential = ManagedIdentityCredential()
                else:
                    # Use user-assigned managed identity
                    self._credential = ManagedIdentityCredential(
                        client_id=self.auth_config.client_id
                    )

            elif (
                self.auth_config.authentication_method
                == AuthenticationMethod.CLIENT_ID_AND_SECRET
            ):
                (
                    DefaultAzureCredential,
                    ManagedIdentityCredential,
                    ClientSecretCredential,
                ) = _import_identity()
                # Type assertion since validation ensures these are not None
                assert self.auth_config.client_id is not None
                assert self.auth_config.client_secret is not None
                assert self.auth_config.tenant_id is not None
                self._credential = ClientSecretCredential(
                    tenant_id=self.auth_config.tenant_id,
                    client_id=self.auth_config.client_id,
                    client_secret=self.auth_config.client_secret,
                )

            elif self.auth_config.authentication_method == AuthenticationMethod.TOKEN:
                # Use AzureKeyCredential for consistent API key handling
                assert self.auth_config.api_key is not None
                self._credential = AzureKeyCredential(self.auth_config.api_key)

            else:
                raise ValueError(
                    f"Unsupported authentication method: {self.auth_config.authentication_method}"
                )

        return self._credential

    @property
    def api_key(self) -> str:
        """
        Get the raw API key string for special cases (like connection strings).

        Returns:
            str: Raw API key/token value.

        Raises:
            ValueError: If authentication method is not TOKEN or api_key is missing.
        """
        if self.auth_config.authentication_method != AuthenticationMethod.TOKEN:
            raise ValueError(
                "API key requires TOKEN authentication method, "
                f"got {self.auth_config.authentication_method}"
            )

        # Use the centralized validation to ensure consistency
        self.auth_config.validate_for_method()

        # Type assertion is safe here because validation ensures api_key is not None
        assert self.auth_config.api_key is not None
        return self.auth_config.api_key

    @property
    def key_credential(self) -> AzureKeyCredential:
        """
        Get AzureKeyCredential specifically for services that only accept AzureKeyCredential.
        """
        if self.auth_config.authentication_method != AuthenticationMethod.TOKEN:
            raise ValueError(
                "key_credential property is only valid for TOKEN authentication method"
            )

        # Use the centralized validation to ensure consistency
        self.auth_config.validate_for_method()

        # Type assertion is safe here because validation ensures api_key is not None
        assert self.auth_config.api_key is not None
        return AzureKeyCredential(self.auth_config.api_key)

    @property
    def token_credential(self) -> TokenCredential:
        """
        Get TokenCredential specifically for services that only accept TokenCredential.

        Returns:
            TokenCredential: Credential object for Azure AD authentication.

        Raises:
            ValueError: If authentication method is TOKEN (use api_key property instead),
                or the resolved object doesn't look like a TokenCredential.
        """
        if self.auth_config.authentication_method == AuthenticationMethod.TOKEN:
            raise ValueError(
                "TOKEN authentication method should use api_key property "
                "for services that need raw API key strings"
            )

        # For non-TOKEN methods, credential will always be TokenCredential-like
        cred = self.credential
        # Duck-typing check to avoid hard runtime dependency on azure-core types
        if not hasattr(cred, "get_token"):
            raise ValueError(f"Expected TokenCredential-like object, got {type(cred)}")

        return cred

    @abstractmethod
    def build(self) -> Any:
        """Build and return the Azure client."""
        raise NotImplementedError
