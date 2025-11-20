"""Memory profiling script to detect memory leaks and analyze memory usage.

This script monitors memory usage patterns during typical operations
to identify potential memory leaks or inefficient memory usage.
"""

import gc
import sys
import time
from pathlib import Path
from typing import List, Tuple

# Add the project root to the path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from profiling_utils import print_section


def get_memory_usage() -> float:
    """Get current process memory usage in MB.

    Returns:
        Memory usage in megabytes.
    """
    try:
        import psutil
        import os

        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024
    except ImportError:
        print("Warning: psutil not available, using basic memory tracking")
        return 0.0


def profile_import_cache_memory() -> None:
    """Profile memory usage of import caching."""
    print_section("Import Cache Memory Usage")

    from ingenious.utils.imports import (
        import_class_with_fallback,
        clear_import_cache,
        get_import_stats,
    )

    gc.collect()
    initial_memory = get_memory_usage()
    print(f"Initial memory: {initial_memory:.2f} MB")

    # Import many classes to populate cache
    modules_to_import = [
        ("models.chat", "IChatRequest"),
        ("models.chat", "IChatResponse"),
        ("models.message", "Message"),
    ]

    print(f"\nImporting {len(modules_to_import)} classes...")
    for module, class_name in modules_to_import:
        try:
            import_class_with_fallback(module, class_name)
        except Exception as e:
            print(f"  Skipped {module}.{class_name}: {e}")

    gc.collect()
    after_import_memory = get_memory_usage()
    stats = get_import_stats()

    print(f"\nAfter imports:")
    print(f"  Memory: {after_import_memory:.2f} MB")
    print(f"  Memory increase: {after_import_memory - initial_memory:.2f} MB")
    print(f"  Classes cached: {stats['classes_cached']}")
    print(f"  Modules cached: {stats['modules_cached']}")

    # Clear cache and check memory
    clear_import_cache()
    gc.collect()
    after_clear_memory = get_memory_usage()

    print(f"\nAfter clearing cache:")
    print(f"  Memory: {after_clear_memory:.2f} MB")
    print(f"  Memory freed: {after_import_memory - after_clear_memory:.2f} MB")

    if after_clear_memory < after_import_memory:
        print("\n✓ Cache cleanup working properly")
    else:
        print("\n⚠ Cache may not be releasing memory properly")


def profile_message_list_memory() -> None:
    """Profile memory usage when handling message lists."""
    print_section("Message List Memory Usage")

    class MockMessage:
        """Mock message for testing."""

        def __init__(self, content: str):
            self.role = "user"
            self.content = content

    gc.collect()
    initial_memory = get_memory_usage()
    print(f"Initial memory: {initial_memory:.2f} MB")

    # Simulate loading progressively larger message lists
    message_counts = [100, 500, 1000, 5000]
    memory_points: List[Tuple[int, float]] = []

    for count in message_counts:
        # Create messages
        messages = [MockMessage("Message content " * 50) for _ in range(count)]

        # Process like in multi_agent service
        memory_parts = []
        for msg in messages[-10:]:
            memory_parts.append(f"{msg.role}: {msg.content[:200]}...")
        result = "\n".join(memory_parts)

        gc.collect()
        current_memory = get_memory_usage()
        memory_increase = current_memory - initial_memory
        memory_points.append((count, memory_increase))

        print(f"\n{count} messages:")
        print(f"  Memory: {current_memory:.2f} MB (+{memory_increase:.2f} MB)")
        print(f"  Per message: {(memory_increase * 1024 / count):.2f} KB")

        # Clean up for next iteration
        del messages
        del memory_parts
        del result
        gc.collect()

    print("\nMemory growth analysis:")
    if len(memory_points) >= 2:
        first_count, first_mem = memory_points[0]
        last_count, last_mem = memory_points[-1]
        growth_rate = (last_mem - first_mem) / (last_count - first_count)
        print(f"  Growth rate: {growth_rate * 1024:.2f} KB per message")

        if growth_rate < 0.005:  # Less than 5KB per message
            print("  ✓ Reasonable memory usage")
        else:
            print("  ⚠ High memory usage per message")


def detect_memory_leaks() -> None:
    """Detect potential memory leaks through repeated operations."""
    print_section("Memory Leak Detection")

    gc.collect()
    initial_memory = get_memory_usage()
    print(f"Initial memory: {initial_memory:.2f} MB")

    # Simulate repeated operations
    iterations = 100
    memory_samples: List[float] = []

    print(f"\nRunning {iterations} iterations of typical operations...")

    for i in range(iterations):
        # Simulate typical operations
        from ingenious.utils.imports import import_class_with_fallback, clear_import_cache

        # Import and clear repeatedly (simulates request lifecycle)
        try:
            import_class_with_fallback("models.chat", "IChatRequest")
        except Exception:
            pass

        if i % 10 == 0:
            clear_import_cache()
            gc.collect()
            current_memory = get_memory_usage()
            memory_samples.append(current_memory)
            print(f"  Iteration {i}: {current_memory:.2f} MB")

    gc.collect()
    final_memory = get_memory_usage()
    memory_increase = final_memory - initial_memory

    print(f"\nFinal memory: {final_memory:.2f} MB")
    print(f"Total increase: {memory_increase:.2f} MB")
    print(f"Increase per iteration: {(memory_increase / iterations * 1024):.2f} KB")

    # Check for steady growth (leak indicator)
    if len(memory_samples) >= 3:
        first_half = sum(memory_samples[: len(memory_samples) // 2]) / (len(memory_samples) // 2)
        second_half = sum(memory_samples[len(memory_samples) // 2 :]) / (
            len(memory_samples) - len(memory_samples) // 2
        )
        trend = second_half - first_half

        print(f"\nMemory trend analysis:")
        print(f"  First half avg: {first_half:.2f} MB")
        print(f"  Second half avg: {second_half:.2f} MB")
        print(f"  Trend: {'+' if trend >= 0 else ''}{trend:.2f} MB")

        if abs(trend) < 5:  # Less than 5MB growth
            print("  ✓ No significant memory leak detected")
        else:
            print("  ⚠ Potential memory leak detected")


def main() -> None:
    """Run all memory profiling tests."""
    try:
        profile_import_cache_memory()
        profile_message_list_memory()
        detect_memory_leaks()

        print_section("Summary")
        print("\nMemory profiling completed successfully.")
        print("Review the results above for potential memory issues.")

    except Exception as e:
        print(f"\nError during profiling: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
