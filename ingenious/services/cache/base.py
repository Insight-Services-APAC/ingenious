"""Base cache service interface.

This module defines the abstract interface for cache implementations.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class CacheService(ABC):
    """Abstract base class for cache service implementations.

    Defines the contract for cache operations that all cache backends
    (memory, Redis, etc.) must implement.
    """

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Retrieve a value from cache by key.

        Args:
            key: Cache key to look up.

        Returns:
            Cached value if found and not expired, None otherwise.
        """
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store a value in cache with optional TTL.

        Args:
            key: Cache key to store value under.
            value: Value to cache (must be JSON serializable).
            ttl: Time-to-live in seconds, None uses default TTL.
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove a value from cache by key.

        Args:
            key: Cache key to delete.
        """
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all cached values."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache.

        Args:
            key: Cache key to check.

        Returns:
            True if key exists and is not expired, False otherwise.
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close cache connections and cleanup resources."""
        pass
