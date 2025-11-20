"""Shared profiling utilities and helpers for performance measurement.

This module provides common functionality for profiling scripts including
timing decorators, metric collection, and result formatting.
"""

import time
import functools
from typing import Any, Callable, Dict, List, TypeVar, cast
from dataclasses import dataclass, field
import statistics

T = TypeVar('T')


@dataclass
class ProfileResult:
    """Container for profiling results."""

    name: str
    duration_ms: float
    memory_mb: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkResults:
    """Container for benchmark statistics."""

    name: str
    samples: List[float]
    p50: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    mean: float = 0.0
    min: float = 0.0
    max: float = 0.0

    def __post_init__(self) -> None:
        """Calculate statistics from samples."""
        if self.samples:
            sorted_samples = sorted(self.samples)
            self.p50 = self._percentile(sorted_samples, 50)
            self.p95 = self._percentile(sorted_samples, 95)
            self.p99 = self._percentile(sorted_samples, 99)
            self.mean = statistics.mean(sorted_samples)
            self.min = min(sorted_samples)
            self.max = max(sorted_samples)

    def _percentile(self, sorted_data: List[float], percentile: float) -> float:
        """Calculate percentile from sorted data."""
        if not sorted_data:
            return 0.0
        index = (percentile / 100) * (len(sorted_data) - 1)
        lower = int(index)
        upper = min(lower + 1, len(sorted_data) - 1)
        weight = index - lower
        return sorted_data[lower] * (1 - weight) + sorted_data[upper] * weight


def time_function(func: Callable[..., T]) -> Callable[..., tuple[T, float]]:
    """Decorator to time function execution.

    Returns:
        Tuple of (result, duration_ms)
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> tuple[T, float]:
        start = time.perf_counter()
        result = func(*args, **kwargs)
        duration = (time.perf_counter() - start) * 1000  # Convert to ms
        return result, duration

    return wrapper


async def time_async_function(func: Callable[..., T]) -> Callable[..., tuple[T, float]]:
    """Decorator to time async function execution.

    Returns:
        Tuple of (result, duration_ms)
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> tuple[T, float]:
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        duration = (time.perf_counter() - start) * 1000  # Convert to ms
        return result, duration

    return cast(Callable[..., tuple[T, float]], wrapper)


def format_results(results: BenchmarkResults) -> str:
    """Format benchmark results as a readable string."""
    return f"""
{results.name}:
  Samples: {len(results.samples)}
  Mean:    {results.mean:.2f}ms
  P50:     {results.p50:.2f}ms
  P95:     {results.p95:.2f}ms
  P99:     {results.p99:.2f}ms
  Min:     {results.min:.2f}ms
  Max:     {results.max:.2f}ms
"""


def print_section(title: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print('=' * 60)
