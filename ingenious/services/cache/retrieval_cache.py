"""Cached wrapper for Azure Search retrieval operations.

This module provides a cached wrapper around Azure Search retrieval
to reduce redundant API calls for identical queries.
"""

from typing import Any, Optional

from ingenious.core.structured_logging import get_logger

from .base import CacheService
from .utils import generate_cache_key

logger = get_logger(__name__)


class CachedRetrieval:
    """Wrapper to add caching to search retrieval operations.

    This class wraps search retrieval operations and adds caching to reduce
    redundant API calls for identical queries.

    Attributes:
        _cache_service: Cache service instance to use.
        _cache_ttl: Time-to-live for cached results in seconds.
    """

    def __init__(
        self,
        cache_service: CacheService,
        cache_ttl: int = 300,
    ) -> None:
        """Initialize cached retrieval wrapper.

        Args:
            cache_service: Cache service instance to use.
            cache_ttl: Time-to-live for cached results in seconds (default: 5 minutes).
        """
        self._cache_service = cache_service
        self._cache_ttl = cache_ttl
        logger.info("Cached retrieval initialized", cache_ttl=cache_ttl)

    async def search_with_cache(
        self,
        search_func: Any,
        query: str,
        cache_key_prefix: str = "search",
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Execute search with caching.

        Args:
            search_func: The async search function to call on cache miss.
            query: The search query.
            cache_key_prefix: Prefix for the cache key.
            **kwargs: Additional parameters for the search function.

        Returns:
            List of search results (from cache or fresh).
        """
        # Generate cache key
        cache_key = generate_cache_key(cache_key_prefix, query, **kwargs)

        # Try to get from cache
        cached_results = await self._cache_service.get(cache_key)
        if cached_results is not None:
            logger.info(
                "Cache hit for search",
                cache_key_prefix=cache_key_prefix,
                query_length=len(query),
                result_count=len(cached_results),
            )
            return cached_results

        # Cache miss - execute search
        logger.info(
            "Cache miss for search",
            cache_key_prefix=cache_key_prefix,
            query_length=len(query),
        )
        results = await search_func(query, **kwargs)

        # Store in cache
        if results:
            await self._cache_service.set(cache_key, results, ttl=self._cache_ttl)
            logger.info(
                "Cached search results",
                cache_key_prefix=cache_key_prefix,
                result_count=len(results),
            )

        return results

    async def get_thread_with_cache(
        self,
        get_thread_func: Any,
        thread_id: str,
        **kwargs: Any,
    ) -> Optional[Any]:
        """Get thread messages with caching.

        Args:
            get_thread_func: The async function to get thread data.
            thread_id: Thread identifier.
            **kwargs: Additional parameters for the get function.

        Returns:
            Thread data (from cache or fresh).
        """
        # Generate cache key
        cache_key = f"thread:{thread_id}:messages"

        # Try to get from cache
        cached_thread = await self._cache_service.get(cache_key)
        if cached_thread is not None:
            logger.info("Cache hit for thread", thread_id=thread_id)
            return cached_thread

        # Cache miss - fetch thread
        logger.info("Cache miss for thread", thread_id=thread_id)
        thread_data = await get_thread_func(thread_id, **kwargs)

        # Store in cache with shorter TTL (1-2 minutes since threads change frequently)
        if thread_data is not None:
            await self._cache_service.set(cache_key, thread_data, ttl=60)
            logger.info("Cached thread data", thread_id=thread_id)

        return thread_data

    async def invalidate_thread_cache(self, thread_id: str) -> None:
        """Invalidate cache for a specific thread.

        This should be called when a thread is modified (e.g., new message added).

        Args:
            thread_id: Thread identifier to invalidate.
        """
        cache_key = f"thread:{thread_id}:messages"
        await self._cache_service.delete(cache_key)
        logger.info("Invalidated thread cache", thread_id=thread_id)
