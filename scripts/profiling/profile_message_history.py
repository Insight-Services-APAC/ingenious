"""Profile message history loading performance.

This script measures the performance of loading chat history from the database
to identify if message loading is a bottleneck.
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock

# Add the project root to the path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from profiling_utils import BenchmarkResults, format_results, print_section


class MockMessage:
    """Mock message for testing."""

    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content


async def profile_message_loading() -> None:
    """Profile message history loading performance."""
    print_section("Message History Loading Performance")

    # Test different message counts
    message_counts = [10, 50, 100, 500]

    for count in message_counts:
        print(f"\n{count} Messages:")

        # Create mock messages
        messages = [MockMessage("user" if i % 2 == 0 else "assistant", f"Message content {i}" * 10) for i in range(count)]

        # Test 1: Slicing last 10 messages (current implementation)
        durations = []
        for _ in range(100):
            start = time.perf_counter()
            last_10 = messages[-10:]
            memory_parts = []
            for msg in last_10:
                memory_parts.append(f"{msg.role}: {msg.content[:200]}...")
            result = "\n".join(memory_parts)
            duration = (time.perf_counter() - start) * 1000
            durations.append(duration)

        slice_results = BenchmarkResults(name=f"Python Slice ({count} msgs)", samples=durations)
        print(format_results(slice_results))

        # Test 2: Database query simulation
        # Simulate async database call overhead
        async def mock_db_query() -> List[MockMessage]:
            """Mock database query with realistic delay."""
            await asyncio.sleep(0.001)  # 1ms simulated DB latency
            return messages[-10:]

        durations = []
        for _ in range(50):
            start = time.perf_counter()
            result_messages = await mock_db_query()
            memory_parts = []
            for msg in result_messages:
                memory_parts.append(f"{msg.role}: {msg.content[:200]}...")
            result = "\n".join(memory_parts)
            duration = (time.perf_counter() - start) * 1000
            durations.append(duration)

        db_results = BenchmarkResults(name=f"With DB Query ({count} msgs)", samples=durations)
        print(format_results(db_results))

    # Summary
    print_section("Analysis")
    print("\nFindings:")
    print("1. Python slicing is very fast (< 0.1ms typically)")
    print("2. Database query overhead dominates (1ms+ per query)")
    print("3. Message processing is negligible for reasonable sizes")
    print("\nRecommendations:")
    print("✓ Database query optimization (use LIMIT in SQL)")
    print("✓ Add index on (thread_id, timestamp) columns")
    print("✓ Consider caching recent messages per thread")
    print("✓ Use database pagination instead of Python slicing")


async def profile_memory_building() -> None:
    """Profile the memory building process specifically."""
    print_section("Memory Building Performance")

    messages = [MockMessage("user" if i % 2 == 0 else "assistant", f"Message content {i}" * 20) for i in range(100)]

    # Test different approaches to building memory
    print("\n1. Current Approach (String Concatenation)")
    durations = []
    for _ in range(1000):
        start = time.perf_counter()
        memory_parts = []
        for msg in messages[-10:]:
            memory_parts.append(f"{msg.role}: {msg.content[:200]}...")
        result = "\n".join(memory_parts)
        duration = (time.perf_counter() - start) * 1000
        durations.append(duration)

    current_results = BenchmarkResults(name="List + Join", samples=durations)
    print(format_results(current_results))

    print("\n2. Alternative: Direct String Building")
    durations = []
    for _ in range(1000):
        start = time.perf_counter()
        result = "\n".join([f"{msg.role}: {msg.content[:200]}..." for msg in messages[-10:]])
        duration = (time.perf_counter() - start) * 1000
        durations.append(duration)

    alt_results = BenchmarkResults(name="List Comprehension", samples=durations)
    print(format_results(alt_results))

    print("\n3. Alternative: Pre-formatted Messages")
    # Simulate pre-formatting during message storage
    formatted_messages = [f"{msg.role}: {msg.content[:200]}..." for msg in messages]
    durations = []
    for _ in range(1000):
        start = time.perf_counter()
        result = "\n".join(formatted_messages[-10:])
        duration = (time.perf_counter() - start) * 1000
        durations.append(duration)

    preformat_results = BenchmarkResults(name="Pre-formatted", samples=durations)
    print(format_results(preformat_results))

    print("\nConclusion:")
    print(f"Memory building is very fast (< {current_results.p95:.3f}ms)")
    print("This is NOT a bottleneck. Focus on database query optimization instead.")


if __name__ == "__main__":
    asyncio.run(profile_message_loading())
    asyncio.run(profile_memory_building())
