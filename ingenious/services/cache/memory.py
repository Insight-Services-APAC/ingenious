"""In-memory cache service implementation using TTLCache.

This module provides an in-memory cache implementation using cachetools.TTLCache
for simple, fast caching without external dependencies.
"""

import json
from typing import Any, Optional

from cachetools import TTLCache

from ingenious.core.structured_logging import get_logger

from .base import CacheService

logger = get_logger(__name__)


class MemoryCacheService(CacheService):
    """In-memory cache implementation using TTLCache.

    This implementation uses cachetools.TTLCache to provide an LRU cache
    with time-to-live expiration. The cache is not shared across processes
    or instances and will be lost on restart.

    Attributes:
        _cache: The underlying TTLCache instance.
        _default_ttl: Default TTL in seconds for cached items.
    """

    def __init__(self, max_size: int = 1000, default_ttl: int = 300) -> None:
        """Initialize memory cache service.

        Args:
            max_size: Maximum number of items to store in cache.
            default_ttl: Default time-to-live in seconds.
        """
        self._cache: TTLCache[str, str] = TTLCache(maxsize=max_size, ttl=default_ttl)
        self._default_ttl = default_ttl
        logger.info(
            "Memory cache initialized",
            max_size=max_size,
            default_ttl=default_ttl,
        )

    async def get(self, key: str) -> Optional[Any]:
        """Retrieve a value from cache by key.

        Args:
            key: Cache key to look up.

        Returns:
            Cached value if found and not expired, None otherwise.
        """
        try:
            cached_value = self._cache.get(key)
            if cached_value is not None:
                logger.debug("Cache hit", key=key)
                return json.loads(cached_value)
            logger.debug("Cache miss", key=key)
            return None
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Cache retrieval error", key=key, error=str(e))
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store a value in cache with optional TTL.

        Note: TTLCache doesn't support per-item TTL, so the ttl parameter
        is ignored and the cache-wide default TTL is used.

        Args:
            key: Cache key to store value under.
            value: Value to cache (must be JSON serializable).
            ttl: Time-to-live in seconds (ignored, uses default TTL).
        """
        try:
            # Serialize value to JSON string
            serialized = json.dumps(value)
            self._cache[key] = serialized
            logger.debug("Cache set", key=key, ttl=self._default_ttl)
        except (TypeError, ValueError) as e:
            logger.error("Cache set error", key=key, error=str(e))

    async def delete(self, key: str) -> None:
        """Remove a value from cache by key.

        Args:
            key: Cache key to delete.
        """
        try:
            if key in self._cache:
                del self._cache[key]
                logger.debug("Cache delete", key=key)
        except KeyError:
            pass

    async def clear(self) -> None:
        """Clear all cached values."""
        self._cache.clear()
        logger.info("Cache cleared")

    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache.

        Args:
            key: Cache key to check.

        Returns:
            True if key exists and is not expired, False otherwise.
        """
        return key in self._cache

    async def close(self) -> None:
        """Close cache connections and cleanup resources."""
        self._cache.clear()
        logger.info("Memory cache closed")
