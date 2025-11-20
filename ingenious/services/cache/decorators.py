"""Cache decorators and helpers for adding caching to functions.

This module provides decorators and helper functions to add caching
to async functions and methods.
"""

from functools import wraps
from typing import Any, Callable, Optional, TypeVar, cast

from ingenious.core.structured_logging import get_logger

from .base import CacheService
from .utils import generate_cache_key

logger = get_logger(__name__)

T = TypeVar("T")


def cached(
    cache_service: CacheService,
    key_prefix: str,
    ttl: Optional[int] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to add caching to async functions.

    Args:
        cache_service: Cache service instance to use.
        key_prefix: Prefix for cache keys.
        ttl: Optional TTL override for cached values.

    Returns:
        Decorated function with caching.

    Example:
        @cached(cache_service, "search_results", ttl=300)
        async def search(query: str, top_k: int) -> list[dict]:
            # Expensive search operation
            return results
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Generate cache key from function arguments
            # Skip 'self' or 'cls' if present
            cache_args = args[1:] if args and hasattr(args[0], "__dict__") else args
            cache_key = generate_cache_key(key_prefix, *cache_args, **kwargs)

            # Try to get from cache
            cached_value = await cache_service.get(cache_key)
            if cached_value is not None:
                logger.debug("Cache hit", key=cache_key, function=func.__name__)
                return cached_value

            # Cache miss - call original function
            logger.debug("Cache miss", key=cache_key, function=func.__name__)
            result = await func(*args, **kwargs)

            # Store in cache
            if result is not None:
                await cache_service.set(cache_key, result, ttl=ttl)

            return result

        return wrapper

    return decorator


async def get_or_set_cache(
    cache_service: CacheService,
    cache_key: str,
    generator_func: Callable[[], Any],
    ttl: Optional[int] = None,
) -> Any:
    """Get value from cache or generate and cache it.

    Args:
        cache_service: Cache service instance to use.
        cache_key: Cache key to look up.
        generator_func: Async function to call if cache miss.
        ttl: Optional TTL for cached value.

    Returns:
        Cached or freshly generated value.

    Example:
        result = await get_or_set_cache(
            cache_service,
            "search:query123",
            lambda: expensive_search(query),
            ttl=300
        )
    """
    # Try to get from cache
    cached_value = await cache_service.get(cache_key)
    if cached_value is not None:
        logger.debug("Cache hit", key=cache_key)
        return cached_value

    # Cache miss - generate value
    logger.debug("Cache miss", key=cache_key)
    result = await generator_func()

    # Store in cache
    if result is not None:
        await cache_service.set(cache_key, result, ttl=ttl)

    return result
