# Response Caching Guide

This guide explains how to use the response caching infrastructure in Ingenious to improve performance and reduce API costs.

## Overview

The caching system provides:
- In-memory LRU cache with TTL support
- Configurable cache backends (memory, Redis-ready)
- Easy integration via decorators and wrappers
- Thread-safe operations
- Cache invalidation support

## Configuration

Add cache configuration to your environment variables or `.env` file:

```bash
# Enable caching
INGENIOUS_CACHE__ENABLED=true

# Backend: 'memory' or 'redis' (redis support coming soon)
INGENIOUS_CACHE__BACKEND=memory

# Default TTL in seconds (5 minutes)
INGENIOUS_CACHE__DEFAULT_TTL=300

# Maximum cache size (in-memory backend)
INGENIOUS_CACHE__MAX_SIZE=1000

# Redis URL (when using redis backend)
INGENIOUS_CACHE__REDIS_URL=redis://localhost:6379
```

## Basic Usage

### 1. Using Cache Decorators

The easiest way to add caching to your async functions:

```python
from ingenious.services.cache import cached, get_cache_service

# Get cache service
cache_service = get_cache_service(config)

# Cache search results for 5 minutes
@cached(cache_service, "search_results", ttl=300)
async def search_documents(query: str, top_k: int) -> list[dict]:
    # Expensive search operation
    results = await expensive_search(query, top_k)
    return results

# First call - cache miss, executes function
results1 = await search_documents("my query", top_k=5)

# Second call with same parameters - cache hit, instant return
results2 = await search_documents("my query", top_k=5)
```

### 2. Using CachedRetrieval Wrapper

For search operations, use the `CachedRetrieval` wrapper:

```python
from ingenious.services.cache import CachedRetrieval, create_cache_service
from ingenious.config import IngeniousSettings

# Initialize
config = IngeniousSettings()
cache_service = create_cache_service(config.cache)
cached_retrieval = CachedRetrieval(cache_service, cache_ttl=300)

# Wrap your search function
async def my_search(query: str) -> list[dict]:
    # Perform actual search
    return await azure_search.search(query)

# Use cached search
results = await cached_retrieval.search_with_cache(
    my_search,
    "query text",
    cache_key_prefix="kb_search"
)
```

### 3. Direct Cache Access

For more control, use the cache service directly:

```python
from ingenious.services.cache import create_cache_service
from ingenious.services.cache.utils import generate_cache_key

cache_service = create_cache_service(config.cache)

# Generate a cache key
cache_key = generate_cache_key("search", query="test", top_k=5)

# Try to get from cache
cached_result = await cache_service.get(cache_key)

if cached_result is None:
    # Cache miss - fetch data
    result = await expensive_operation()
    
    # Store in cache
    await cache_service.set(cache_key, result, ttl=300)
else:
    # Cache hit - use cached data
    result = cached_result
```

## Cache Key Generation

Use utility functions to generate consistent cache keys:

```python
from ingenious.services.cache.utils import (
    generate_cache_key,
    generate_kb_search_cache_key,
    generate_thread_cache_key,
    generate_template_cache_key,
)

# Generic cache key
key = generate_cache_key("prefix", "arg1", "arg2", param1="value1")

# Knowledge base search cache key
key = generate_kb_search_cache_key("query text", top_k=5, knowledge_base_path="kb1")

# Thread messages cache key
key = generate_thread_cache_key("thread_123")

# Template file cache key
key = generate_template_cache_key("rev_456", "template.txt")
```

## Cache Invalidation

Invalidate cache entries when data changes:

```python
from ingenious.services.cache import CachedRetrieval

cached_retrieval = CachedRetrieval(cache_service)

# Add a message to thread
await add_message_to_thread(thread_id, message)

# Invalidate thread cache so next fetch gets fresh data
await cached_retrieval.invalidate_thread_cache(thread_id)
```

## FastAPI Integration

The cache service is available as a FastAPI dependency:

```python
from fastapi import Depends
from ingenious.services.fastapi_dependencies import get_cache_service
from ingenious.services.cache import CacheService

@router.get("/search")
async def search_endpoint(
    query: str,
    cache_service: CacheService = Depends(get_cache_service)
) -> dict:
    cache_key = f"search:{query}"
    
    # Try cache first
    cached = await cache_service.get(cache_key)
    if cached:
        return cached
    
    # Perform search
    results = await perform_search(query)
    
    # Cache results
    await cache_service.set(cache_key, results, ttl=300)
    
    return results
```

## Performance Considerations

### Cache Hit Rates

Monitor cache effectiveness:

```python
# The cache service logs hit/miss events at DEBUG level
# Check logs for:
# - "Cache hit" - successful cache retrieval
# - "Cache miss" - cache lookup failed, data fetched fresh
```

### TTL Guidelines

Recommended TTL values based on data volatility:

- **Search Results**: 5-15 minutes (300-900 seconds)
  - Knowledge base queries rarely change
  - Balances freshness with performance

- **Thread Messages**: 1-2 minutes (60-120 seconds)
  - Threads are actively modified
  - Short TTL ensures reasonably fresh data

- **Template Files**: 1 hour (3600 seconds)
  - Templates change infrequently
  - Longer TTL reduces file I/O

- **User Sessions**: 15-30 minutes (900-1800 seconds)
  - Active session data
  - Balances security with UX

### Memory Usage

For in-memory cache, the `max_size` setting controls memory usage:

```bash
# Rough memory estimation
# Each cached item: ~1-10 KB (depends on data)
# max_size=1000 → ~1-10 MB memory usage
# max_size=10000 → ~10-100 MB memory usage
```

## Best Practices

1. **Use appropriate TTLs**: Balance freshness vs. performance
2. **Invalidate on writes**: Clear cache when data changes
3. **Monitor cache metrics**: Track hit rates to tune settings
4. **Use descriptive key prefixes**: Makes debugging easier
5. **Handle cache failures gracefully**: Always have fallback to fetch fresh data

## Troubleshooting

### Cache Not Working

Check configuration:

```python
from ingenious.config import IngeniousSettings

settings = IngeniousSettings()
print(f"Cache enabled: {settings.cache.enabled}")
print(f"Cache backend: {settings.cache.backend}")
```

### High Memory Usage

Reduce `max_size` or implement more aggressive TTLs:

```bash
INGENIOUS_CACHE__MAX_SIZE=500
INGENIOUS_CACHE__DEFAULT_TTL=180
```

### Stale Data

Ensure cache invalidation happens on data modifications:

```python
# After modifying data
await cache_service.delete(cache_key)

# Or clear all cache
await cache_service.clear()
```

## Future Enhancements

Planned features:

- Redis backend support for distributed caching
- Semantic caching (cache similar queries together)
- Cache warming strategies
- Multi-tier caching (memory + Redis)
- Cache statistics and monitoring dashboard
