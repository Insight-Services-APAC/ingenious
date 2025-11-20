"""Example: Using response caching in Ingenious.

This example demonstrates how to use the caching system to improve
performance for knowledge base searches and thread operations.
"""

import asyncio

from ingenious.config import IngeniousSettings
from ingenious.services.cache import CachedRetrieval, create_cache_service


async def example_knowledge_base_caching() -> None:
    """Example: Caching knowledge base search results."""
    print("\n=== Knowledge Base Search Caching Example ===\n")

    # Initialize cache configuration directly
    from ingenious.config.settings import CacheSettings

    cache_config = CacheSettings(
        enabled=True, backend="memory", default_ttl=300, max_size=1000
    )

    # Create cache service
    cache_service = create_cache_service(cache_config)
    cached_retrieval = CachedRetrieval(cache_service, cache_ttl=300)

    # Simulate an expensive knowledge base search
    search_count = 0

    async def expensive_kb_search(query: str, top_k: int = 5) -> list[dict[str, str]]:
        """Simulate expensive knowledge base search."""
        nonlocal search_count
        search_count += 1

        print(f"  Executing expensive search #{search_count}...")
        await asyncio.sleep(1)  # Simulate network delay

        # Return mock results
        return [
            {"id": f"doc_{i}", "content": f"Result {i} for query: {query}", "score": 0.9 - i * 0.1}
            for i in range(top_k)
        ]

    # First search - cache miss
    print("1. First search (cache miss):")
    results1 = await cached_retrieval.search_with_cache(
        expensive_kb_search, "what is machine learning", cache_key_prefix="kb_search", top_k=5
    )
    print(f"   Found {len(results1)} results")
    print(f"   Total searches executed: {search_count}")

    # Second search with same query - cache hit
    print("\n2. Second search with same query (cache hit):")
    results2 = await cached_retrieval.search_with_cache(
        expensive_kb_search, "what is machine learning", cache_key_prefix="kb_search", top_k=5
    )
    print(f"   Found {len(results2)} results")
    print(f"   Total searches executed: {search_count}")  # Should still be 1

    # Different query - cache miss
    print("\n3. Different query (cache miss):")
    results3 = await cached_retrieval.search_with_cache(
        expensive_kb_search, "explain neural networks", cache_key_prefix="kb_search", top_k=5
    )
    print(f"   Found {len(results3)} results")
    print(f"   Total searches executed: {search_count}")  # Should be 2

    await cache_service.close()


async def example_thread_caching_with_invalidation() -> None:
    """Example: Caching thread messages with cache invalidation."""
    print("\n=== Thread Caching with Invalidation Example ===\n")

    # Initialize cache configuration directly
    from ingenious.config.settings import CacheSettings

    cache_config = CacheSettings(enabled=True, backend="memory")

    # Create cache service
    cache_service = create_cache_service(cache_config)
    cached_retrieval = CachedRetrieval(cache_service, cache_ttl=60)

    # Simulate thread storage
    thread_messages = {"thread_123": ["Hello", "How are you?"]}

    # Simulate getting thread messages
    fetch_count = 0

    async def get_thread_messages(thread_id: str) -> list[str]:
        """Simulate fetching thread messages."""
        nonlocal fetch_count
        fetch_count += 1

        print(f"  Fetching thread from database (fetch #{fetch_count})...")
        await asyncio.sleep(0.5)  # Simulate database query

        return thread_messages.get(thread_id, [])

    # First fetch - cache miss
    print("1. First fetch (cache miss):")
    messages1 = await cached_retrieval.get_thread_with_cache(get_thread_messages, "thread_123")
    print(f"   Messages: {messages1}")
    print(f"   Total fetches: {fetch_count}")

    # Second fetch - cache hit
    print("\n2. Second fetch (cache hit):")
    messages2 = await cached_retrieval.get_thread_with_cache(get_thread_messages, "thread_123")
    print(f"   Messages: {messages2}")
    print(f"   Total fetches: {fetch_count}")  # Should still be 1

    # Add a message to the thread
    print("\n3. Adding new message to thread...")
    thread_messages["thread_123"].append("I'm doing great!")

    # Invalidate the cache for this thread
    print("   Invalidating thread cache...")
    await cached_retrieval.invalidate_thread_cache("thread_123")

    # Fetch again - should get fresh data
    print("\n4. Fetch after invalidation (cache miss, fresh data):")
    messages3 = await cached_retrieval.get_thread_with_cache(get_thread_messages, "thread_123")
    print(f"   Messages: {messages3}")
    print(f"   Total fetches: {fetch_count}")  # Should be 2

    await cache_service.close()


async def example_direct_cache_usage() -> None:
    """Example: Direct cache service usage."""
    print("\n=== Direct Cache Service Usage Example ===\n")

    # Initialize cache configuration directly
    from ingenious.config.settings import CacheSettings

    cache_config = CacheSettings(enabled=True)

    cache_service = create_cache_service(cache_config)

    # Store some data
    print("1. Storing data in cache:")
    await cache_service.set("user:123:profile", {"name": "Alice", "role": "admin"}, ttl=300)
    print("   Stored user profile")

    # Retrieve data
    print("\n2. Retrieving data from cache:")
    profile = await cache_service.get("user:123:profile")
    print(f"   Retrieved: {profile}")

    # Check existence
    print("\n3. Checking cache existence:")
    exists = await cache_service.exists("user:123:profile")
    print(f"   Key exists: {exists}")

    # Delete specific key
    print("\n4. Deleting cache entry:")
    await cache_service.delete("user:123:profile")
    exists_after = await cache_service.exists("user:123:profile")
    print(f"   Key exists after delete: {exists_after}")

    # Clear all cache
    print("\n5. Clearing all cache:")
    await cache_service.set("key1", "value1")
    await cache_service.set("key2", "value2")
    await cache_service.clear()
    print("   All cache cleared")

    await cache_service.close()


async def main() -> None:
    """Run all examples."""
    print("=" * 60)
    print("Ingenious Cache System Examples")
    print("=" * 60)

    await example_knowledge_base_caching()
    await example_thread_caching_with_invalidation()
    await example_direct_cache_usage()

    print("\n" + "=" * 60)
    print("Examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
