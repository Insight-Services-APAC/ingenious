"""Basic load testing script to measure performance under load.

This script simulates concurrent requests to measure system performance
and identify bottlenecks under load.
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import List

# Add the project root to the path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from profiling_utils import BenchmarkResults, format_results, print_section


async def simulate_request(request_id: int, delay_ms: float = 10.0) -> float:
    """Simulate a single request with processing time.

    Args:
        request_id: Unique identifier for the request.
        delay_ms: Simulated processing delay in milliseconds.

    Returns:
        Duration of the request in milliseconds.
    """
    start = time.perf_counter()

    # Simulate request processing
    await asyncio.sleep(delay_ms / 1000)

    # Simulate import overhead (if any)
    from ingenious.utils.imports import import_class_with_fallback

    try:
        import_class_with_fallback("models.chat", "IChatRequest")
    except Exception:
        pass

    duration = (time.perf_counter() - start) * 1000
    return duration


async def run_concurrent_requests(num_requests: int, concurrency: int) -> List[float]:
    """Run multiple concurrent requests.

    Args:
        num_requests: Total number of requests to execute.
        concurrency: Maximum concurrent requests.

    Returns:
        List of request durations in milliseconds.
    """
    durations: List[float] = []
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded_request(request_id: int) -> float:
        async with semaphore:
            return await simulate_request(request_id)

    tasks = [bounded_request(i) for i in range(num_requests)]
    durations = await asyncio.gather(*tasks)

    return list(durations)


async def profile_load() -> None:
    """Profile system performance under various load conditions."""
    print_section("Load Testing")

    # Test configurations
    test_configs = [
        (10, 1, "Sequential (1 concurrent)"),
        (50, 5, "Low Concurrency (5 concurrent)"),
        (100, 10, "Medium Concurrency (10 concurrent)"),
        (100, 25, "High Concurrency (25 concurrent)"),
    ]

    for num_requests, concurrency, description in test_configs:
        print(f"\n{description}")
        print(f"  Requests: {num_requests}, Concurrency: {concurrency}")

        start_time = time.perf_counter()
        durations = await run_concurrent_requests(num_requests, concurrency)
        total_time = (time.perf_counter() - start_time) * 1000

        results = BenchmarkResults(name=description, samples=durations)
        print(format_results(results))

        throughput = num_requests / (total_time / 1000)
        print(f"  Total time: {total_time:.2f}ms")
        print(f"  Throughput: {throughput:.2f} req/sec")

        # Check for performance degradation
        if results.p95 > results.p50 * 2:
            print("  ⚠ High variance detected (P95 > 2x P50)")
        else:
            print("  ✓ Consistent performance")


async def profile_import_under_load() -> None:
    """Profile import performance specifically under concurrent load."""
    print_section("Import Performance Under Load")

    from ingenious.utils.imports import clear_import_cache, get_import_stats

    print("\nTest 1: Cold Cache Under Load")
    clear_import_cache()

    async def import_task(task_id: int) -> float:
        start = time.perf_counter()
        from ingenious.utils.imports import import_class_with_fallback

        try:
            import_class_with_fallback("models.chat", "IChatRequest")
        except Exception:
            pass
        return (time.perf_counter() - start) * 1000

    # Cold cache
    tasks = [import_task(i) for i in range(50)]
    durations = await asyncio.gather(*tasks)
    cold_results = BenchmarkResults(name="Cold Cache (50 concurrent)", samples=durations)
    print(format_results(cold_results))

    print("\nTest 2: Warm Cache Under Load")
    # Warm up cache
    from ingenious.utils.imports import import_class_with_fallback

    try:
        import_class_with_fallback("models.chat", "IChatRequest")
    except Exception:
        pass

    tasks = [import_task(i) for i in range(50)]
    durations = await asyncio.gather(*tasks)
    warm_results = BenchmarkResults(name="Warm Cache (50 concurrent)", samples=durations)
    print(format_results(warm_results))

    stats = get_import_stats()
    print("\nCache Statistics:")
    print(f"  Classes cached: {stats['classes_cached']}")
    print(f"  Modules cached: {stats['modules_cached']}")

    print("\nAnalysis:")
    speedup = cold_results.p50 / warm_results.p50 if warm_results.p50 > 0 else 0
    print(f"  Cache speedup: {speedup:.1f}x")
    if warm_results.p50 < 0.1:
        print("  ✓ Caching is highly effective")
    elif warm_results.p50 < 1.0:
        print("  ✓ Caching is effective")
    else:
        print("  ⚠ Caching overhead still significant")


async def profile_memory_under_load() -> None:
    """Profile memory usage patterns under load."""
    print_section("Memory Usage Under Load")

    try:
        import psutil
        import os

        process = psutil.Process(os.getpid())

        initial_memory = process.memory_info().rss / 1024 / 1024
        print(f"Initial memory: {initial_memory:.2f} MB")

        # Run concurrent requests and monitor memory
        print("\nRunning 200 concurrent requests...")
        await run_concurrent_requests(200, 50)

        peak_memory = process.memory_info().rss / 1024 / 1024
        print(f"Peak memory: {peak_memory:.2f} MB")
        print(f"Memory increase: {peak_memory - initial_memory:.2f} MB")

        # Run garbage collection
        import gc

        gc.collect()
        await asyncio.sleep(0.5)

        after_gc_memory = process.memory_info().rss / 1024 / 1024
        print(f"After GC: {after_gc_memory:.2f} MB")
        print(f"Memory freed: {peak_memory - after_gc_memory:.2f} MB")

        if after_gc_memory - initial_memory < 5:  # Less than 5MB retained
            print("✓ Good memory cleanup")
        else:
            print("⚠ Some memory not released")

    except ImportError:
        print("psutil not available, skipping memory profiling")


async def main() -> None:
    """Run all load tests."""
    try:
        await profile_load()
        await profile_import_under_load()
        await profile_memory_under_load()

        print_section("Load Testing Summary")
        print("\nLoad testing completed successfully.")
        print("Review the results above for performance characteristics under load.")

    except Exception as e:
        print(f"\nError during load testing: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
