"""Profile dynamic import performance to measure overhead.

This script measures the performance of the import_class_with_fallback
function to determine if dynamic imports are a bottleneck.
"""

import sys
import time
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from profiling_utils import BenchmarkResults, format_results, print_section


def profile_import_overhead() -> None:
    """Profile the overhead of dynamic imports."""
    from ingenious.utils.imports import (
        import_class_with_fallback,
        clear_import_cache,
        get_import_stats,
    )

    print_section("Dynamic Import Performance Profiling")

    # Test 1: First import (cold cache)
    print("\n1. First Import (Cold Cache)")
    clear_import_cache()
    durations = []
    for _ in range(10):
        clear_import_cache()
        start = time.perf_counter()
        try:
            import_class_with_fallback(
                "services.chat_services.multi_agent.service",
                "multi_agent_chat_service",
            )
        except Exception as e:
            print(f"Import failed: {e}")
            # Try a different class that exists
            import_class_with_fallback("models.chat", "IChatRequest")
        duration = (time.perf_counter() - start) * 1000
        durations.append(duration)

    cold_results = BenchmarkResults(name="Cold Cache Import", samples=durations)
    print(format_results(cold_results))

    # Test 2: Cached imports (warm cache)
    print("\n2. Cached Import (Warm Cache)")
    clear_import_cache()
    # First import to populate cache
    try:
        import_class_with_fallback(
            "services.chat_services.multi_agent.service",
            "multi_agent_chat_service",
        )
    except Exception:
        import_class_with_fallback("models.chat", "IChatRequest")

    durations = []
    for _ in range(100):
        start = time.perf_counter()
        try:
            import_class_with_fallback(
                "services.chat_services.multi_agent.service",
                "multi_agent_chat_service",
            )
        except Exception:
            import_class_with_fallback("models.chat", "IChatRequest")
        duration = (time.perf_counter() - start) * 1000
        durations.append(duration)

    warm_results = BenchmarkResults(name="Warm Cache Import", samples=durations)
    print(format_results(warm_results))

    # Test 3: Cache statistics
    print("\n3. Cache Statistics")
    stats = get_import_stats()
    print(f"  Modules cached: {stats['modules_cached']}")
    print(f"  Classes cached: {stats['classes_cached']}")
    print(f"  Failed imports: {stats['failed_imports']}")
    print(f"  Spec cache: {stats['spec_cache_info']}")

    # Test 4: Compare with standard import
    print("\n4. Standard Import (Baseline)")
    durations = []
    for _ in range(100):
        start = time.perf_counter()
        from ingenious.models.chat import IChatRequest  # noqa: F401
        duration = (time.perf_counter() - start) * 1000
        durations.append(duration)

    standard_results = BenchmarkResults(name="Standard Import", samples=durations)
    print(format_results(standard_results))

    # Summary
    print_section("Summary")
    overhead = warm_results.p50 - standard_results.p50
    overhead_pct = (overhead / standard_results.p50 * 100) if standard_results.p50 > 0 else 0
    print(f"\nCaching Effectiveness:")
    print(f"  Cold vs Warm Cache: {cold_results.p50 / warm_results.p50:.1f}x faster with cache")
    print(f"\nOverhead Analysis:")
    print(f"  Warm cache overhead: {overhead:.4f}ms ({overhead_pct:.1f}%)")
    print(f"  Per-request impact (1 import): ~{warm_results.p50:.4f}ms")

    if warm_results.p50 < 0.1:
        print("\n✓ Dynamic imports are well-optimized (< 0.1ms overhead)")
    elif warm_results.p50 < 1.0:
        print("\n⚠ Dynamic imports have minor overhead (< 1ms)")
    else:
        print("\n✗ Dynamic imports are a bottleneck (> 1ms overhead)")


if __name__ == "__main__":
    profile_import_overhead()
