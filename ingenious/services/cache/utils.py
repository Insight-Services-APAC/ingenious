"""Cache utility functions for key generation and hashing.

This module provides utility functions for generating consistent cache keys
from various input parameters.
"""

import hashlib
import json
from typing import Any


def generate_cache_key(prefix: str, *args: Any, **kwargs: Any) -> str:
    """Generate a consistent cache key from prefix and parameters.

    Args:
        prefix: Prefix for the cache key (e.g., 'kb_search', 'thread').
        *args: Positional arguments to include in key.
        **kwargs: Keyword arguments to include in key.

    Returns:
        SHA256 hash-based cache key with prefix.

    Example:
        >>> generate_cache_key('search', 'query text', top_k=5)
        'search:a1b2c3d4...'
    """
    # Combine all parameters into a stable string representation
    key_parts = [str(arg) for arg in args]
    key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
    key_data = ":".join(key_parts)

    # Generate hash of the key data
    key_hash = hashlib.sha256(key_data.encode()).hexdigest()

    # Return prefixed key
    return f"{prefix}:{key_hash}"


def generate_kb_search_cache_key(query: str, top_k: int, knowledge_base_path: str = "") -> str:
    """Generate cache key for knowledge base search results.

    Args:
        query: Search query text.
        top_k: Number of results to retrieve.
        knowledge_base_path: Optional path to knowledge base.

    Returns:
        Cache key for this search.
    """
    return generate_cache_key("kb_search", query, top_k=top_k, kb_path=knowledge_base_path)


def generate_thread_cache_key(thread_id: str) -> str:
    """Generate cache key for thread message history.

    Args:
        thread_id: Thread identifier.

    Returns:
        Cache key for this thread.
    """
    return f"thread:{thread_id}:messages"


def generate_template_cache_key(revision_id: str, filename: str) -> str:
    """Generate cache key for template files.

    Args:
        revision_id: Revision identifier.
        filename: Template filename.

    Returns:
        Cache key for this template.
    """
    return f"template:{revision_id}:{filename}"


def serialize_for_cache(value: Any) -> str:
    """Serialize a value for storage in cache.

    Args:
        value: Value to serialize.

    Returns:
        JSON string representation.

    Raises:
        TypeError: If value is not JSON serializable.
    """
    return json.dumps(value)


def deserialize_from_cache(value: str) -> Any:
    """Deserialize a value from cache storage.

    Args:
        value: JSON string from cache.

    Returns:
        Deserialized Python object.

    Raises:
        json.JSONDecodeError: If value is not valid JSON.
    """
    return json.loads(value)
