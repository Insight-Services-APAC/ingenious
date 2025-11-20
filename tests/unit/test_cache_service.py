"""Tests for the cache service module.

This test suite validates the cache service implementation including
configuration, cache operations, and key generation utilities.
"""

from typing import Any

import pytest

from ingenious.config.settings import CacheSettings
from ingenious.services.cache import MemoryCacheService, create_cache_service
from ingenious.services.cache.factory import NullCacheService
from ingenious.services.cache.utils import (
    generate_cache_key,
    generate_kb_search_cache_key,
    generate_template_cache_key,
    generate_thread_cache_key,
)


class TestCacheSettings:
    """Test cache configuration settings."""

    def test_default_cache_settings(self) -> None:
        """Test creating cache settings with defaults."""
        settings = CacheSettings()

        assert settings.enabled is False
        assert settings.backend == "memory"
        assert settings.default_ttl == 300
        assert settings.max_size == 1000

    def test_cache_settings_validation(self) -> None:
        """Test cache settings validation."""
        # Valid settings
        settings = CacheSettings(
            enabled=True,
            backend="memory",
            default_ttl=600,
            max_size=2000,
        )
        assert settings.enabled is True
        assert settings.default_ttl == 600

        # Invalid backend
        with pytest.raises(ValueError, match="Cache backend must be one of"):
            CacheSettings(backend="invalid")

        # Invalid TTL
        with pytest.raises(ValueError, match="Default TTL must be non-negative"):
            CacheSettings(default_ttl=-1)

        # Invalid max_size
        with pytest.raises(ValueError, match="Max cache size must be at least 1"):
            CacheSettings(max_size=0)


class TestMemoryCacheService:
    """Test in-memory cache service implementation."""

    @pytest.mark.asyncio
    async def test_cache_set_and_get(self) -> None:
        """Test setting and getting values from cache."""
        cache = MemoryCacheService(max_size=100, default_ttl=300)

        # Test cache miss
        value = await cache.get("test_key")
        assert value is None

        # Test cache set and hit
        await cache.set("test_key", {"data": "test_value"})
        value = await cache.get("test_key")
        assert value == {"data": "test_value"}

        await cache.close()

    @pytest.mark.asyncio
    async def test_cache_delete(self) -> None:
        """Test deleting values from cache."""
        cache = MemoryCacheService(max_size=100, default_ttl=300)

        await cache.set("test_key", "test_value")
        assert await cache.exists("test_key")

        await cache.delete("test_key")
        assert not await cache.exists("test_key")
        assert await cache.get("test_key") is None

        await cache.close()

    @pytest.mark.asyncio
    async def test_cache_clear(self) -> None:
        """Test clearing all cache values."""
        cache = MemoryCacheService(max_size=100, default_ttl=300)

        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        assert await cache.exists("key1")
        assert await cache.exists("key2")

        await cache.clear()
        assert not await cache.exists("key1")
        assert not await cache.exists("key2")

        await cache.close()

    @pytest.mark.asyncio
    async def test_cache_exists(self) -> None:
        """Test checking if key exists in cache."""
        cache = MemoryCacheService(max_size=100, default_ttl=300)

        assert not await cache.exists("test_key")

        await cache.set("test_key", "value")
        assert await cache.exists("test_key")

        await cache.close()

    @pytest.mark.asyncio
    async def test_cache_json_serialization(self) -> None:
        """Test caching complex data structures."""
        cache = MemoryCacheService(max_size=100, default_ttl=300)

        # Test with nested dict
        complex_data = {
            "nested": {"key": "value"},
            "list": [1, 2, 3],
            "string": "test",
            "number": 42,
        }
        await cache.set("complex_key", complex_data)
        retrieved = await cache.get("complex_key")
        assert retrieved == complex_data

        await cache.close()


class TestCacheFactory:
    """Test cache factory functions."""

    def test_create_memory_cache(self) -> None:
        """Test creating memory cache service."""
        config = CacheSettings(
            enabled=True,
            backend="memory",
            max_size=500,
            default_ttl=200,
        )
        cache = create_cache_service(config)

        assert isinstance(cache, MemoryCacheService)

    def test_create_disabled_cache(self) -> None:
        """Test creating cache when disabled."""
        config = CacheSettings(enabled=False)
        cache = create_cache_service(config)

        assert isinstance(cache, NullCacheService)

    def test_create_redis_cache_fallback(self) -> None:
        """Test that Redis backend falls back to memory (not yet implemented)."""
        config = CacheSettings(
            enabled=True,
            backend="redis",
            max_size=500,
            default_ttl=200,
        )
        cache = create_cache_service(config)

        # Should fall back to memory cache
        assert isinstance(cache, MemoryCacheService)


class TestNullCacheService:
    """Test null cache service (no-op implementation)."""

    @pytest.mark.asyncio
    async def test_null_cache_operations(self) -> None:
        """Test that null cache does nothing."""
        cache = NullCacheService()

        # All operations should be no-ops
        await cache.set("key", "value")
        assert await cache.get("key") is None
        assert not await cache.exists("key")

        await cache.delete("key")
        await cache.clear()
        await cache.close()


class TestCacheUtils:
    """Test cache utility functions."""

    def test_generate_cache_key(self) -> None:
        """Test generating cache keys from parameters."""
        # Test with positional args
        key1 = generate_cache_key("prefix", "arg1", "arg2")
        key2 = generate_cache_key("prefix", "arg1", "arg2")
        assert key1 == key2
        assert key1.startswith("prefix:")

        # Test with kwargs
        key3 = generate_cache_key("prefix", param1="value1", param2="value2")
        key4 = generate_cache_key("prefix", param2="value2", param1="value1")
        assert key3 == key4  # Order shouldn't matter

        # Different parameters should give different keys
        key5 = generate_cache_key("prefix", "different")
        assert key1 != key5

    def test_generate_kb_search_cache_key(self) -> None:
        """Test generating knowledge base search cache keys."""
        key1 = generate_kb_search_cache_key("query text", top_k=5)
        key2 = generate_kb_search_cache_key("query text", top_k=5)
        assert key1 == key2
        assert key1.startswith("kb_search:")

        # Different parameters should give different keys
        key3 = generate_kb_search_cache_key("query text", top_k=10)
        assert key1 != key3

        key4 = generate_kb_search_cache_key("different query", top_k=5)
        assert key1 != key4

    def test_generate_thread_cache_key(self) -> None:
        """Test generating thread cache keys."""
        key1 = generate_thread_cache_key("thread123")
        key2 = generate_thread_cache_key("thread123")
        assert key1 == key2
        assert key1 == "thread:thread123:messages"

        key3 = generate_thread_cache_key("thread456")
        assert key1 != key3

    def test_generate_template_cache_key(self) -> None:
        """Test generating template cache keys."""
        key1 = generate_template_cache_key("rev123", "template.txt")
        key2 = generate_template_cache_key("rev123", "template.txt")
        assert key1 == key2
        assert key1 == "template:rev123:template.txt"

        key3 = generate_template_cache_key("rev456", "template.txt")
        assert key1 != key3


class TestCachedRetrieval:
    """Test cached retrieval wrapper."""

    @pytest.mark.asyncio
    async def test_search_with_cache_hit(self) -> None:
        """Test cached search with cache hit."""
        from ingenious.services.cache import CachedRetrieval

        cache = MemoryCacheService(max_size=100, default_ttl=300)
        cached_retrieval = CachedRetrieval(cache, cache_ttl=300)

        # Mock search function
        call_count = 0

        async def mock_search(query: str) -> list[dict[str, Any]]:
            nonlocal call_count
            call_count += 1
            return [{"result": f"result for {query}"}]

        # First call - cache miss
        result1 = await cached_retrieval.search_with_cache(
            mock_search, "test query", cache_key_prefix="test_search"
        )
        assert call_count == 1
        assert result1 == [{"result": "result for test query"}]

        # Second call - cache hit
        result2 = await cached_retrieval.search_with_cache(
            mock_search, "test query", cache_key_prefix="test_search"
        )
        assert call_count == 1  # Should not call search again
        assert result2 == result1

        await cache.close()

    @pytest.mark.asyncio
    async def test_thread_cache_invalidation(self) -> None:
        """Test thread cache invalidation."""
        from ingenious.services.cache import CachedRetrieval

        cache = MemoryCacheService(max_size=100, default_ttl=300)
        cached_retrieval = CachedRetrieval(cache, cache_ttl=60)

        # Mock get thread function
        async def mock_get_thread(thread_id: str) -> dict[str, Any]:
            return {"thread_id": thread_id, "messages": ["msg1", "msg2"]}

        # Get thread - cache miss
        result1 = await cached_retrieval.get_thread_with_cache(mock_get_thread, "thread123")
        assert result1 == {"thread_id": "thread123", "messages": ["msg1", "msg2"]}

        # Verify it's cached
        assert await cache.exists("thread:thread123:messages")

        # Invalidate cache
        await cached_retrieval.invalidate_thread_cache("thread123")

        # Verify it's no longer cached
        assert not await cache.exists("thread:thread123:messages")

        await cache.close()
