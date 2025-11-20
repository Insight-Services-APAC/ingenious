"""Factory for creating cache service instances.

This module provides a factory function for creating cache service instances
based on configuration settings.
"""

from ingenious.config.settings import CacheSettings
from ingenious.core.structured_logging import get_logger

from .base import CacheService
from .memory import MemoryCacheService

logger = get_logger(__name__)


def create_cache_service(config: CacheSettings) -> CacheService:
    """Create a cache service instance based on configuration.

    Args:
        config: Cache configuration settings.

    Returns:
        Configured cache service instance.

    Raises:
        ValueError: If cache backend is not supported.
    """
    if not config.enabled:
        logger.info("Cache is disabled, creating null cache service")
        return NullCacheService()

    backend = config.backend.lower()

    if backend == "memory":
        logger.info(
            "Creating in-memory cache service",
            max_size=config.max_size,
            default_ttl=config.default_ttl,
        )
        return MemoryCacheService(
            max_size=config.max_size,
            default_ttl=config.default_ttl,
        )
    elif backend == "redis":
        # Redis backend can be implemented in the future
        logger.warning("Redis backend not yet implemented, falling back to memory cache")
        return MemoryCacheService(
            max_size=config.max_size,
            default_ttl=config.default_ttl,
        )
    else:
        raise ValueError(f"Unsupported cache backend: {backend}")


class NullCacheService(CacheService):
    """No-op cache service for when caching is disabled.

    This implementation does nothing and always returns None for cache gets.
    Used when caching is disabled in configuration.
    """

    async def get(self, key: str) -> None:
        """Always return None (cache miss)."""
        return None

    async def set(self, key: str, value: object, ttl: int | None = None) -> None:
        """Do nothing."""
        pass

    async def delete(self, key: str) -> None:
        """Do nothing."""
        pass

    async def clear(self) -> None:
        """Do nothing."""
        pass

    async def exists(self, key: str) -> bool:
        """Always return False."""
        return False

    async def close(self) -> None:
        """Do nothing."""
        pass
