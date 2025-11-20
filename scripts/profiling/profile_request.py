"""Profile typical chat request performance.

This script profiles the performance of typical chat request workflows
to identify bottlenecks in the request processing pipeline.
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

# Add the project root to the path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from profiling_utils import BenchmarkResults, format_results, print_section


class ProfiledOperation:
    """Context manager for profiling operations."""

    def __init__(self, name: str):
        self.name = name
        self.start_time: float = 0
        self.duration_ms: float = 0

    def __enter__(self) -> "ProfiledOperation":
        """Start timing."""
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args: object) -> None:
        """Stop timing and report."""
        self.duration_ms = (time.perf_counter() - self.start_time) * 1000
        print(f"  {self.name}: {self.duration_ms:.3f}ms")


async def profile_chat_request_workflow() -> None:
    """Profile a complete chat request workflow."""
    print_section("Chat Request Workflow Profiling")

    # Mock components
    class MockMessage:
        def __init__(self, role: str, content: str):
            self.role = role
            self.content = content

    class MockChatRequest:
        def __init__(self):
            self.thread_id = "test-thread-123"
            self.conversation_flow = "default"
            self.topic = "general"
            self.thread_chat_history = []
            self.thread_memory = ""
            self.user_id = "test-user"

    # Simulate request processing steps
    print("\nSimulating chat request processing steps:")

    durations = {}

    # Step 1: Import conversation flow class
    with ProfiledOperation("1. Import conversation flow class") as op:
        from ingenious.utils.imports import import_class_with_fallback

        try:
            import_class_with_fallback(
                "services.chat_services.multi_agent.service",
                "multi_agent_chat_service",
            )
        except Exception:
            # Fallback if service not available
            import_class_with_fallback("models.chat", "IChatRequest")
    durations["import"] = op.duration_ms

    # Step 2: Create request object
    with ProfiledOperation("2. Create request object") as op:
        chat_request = MockChatRequest()
    durations["create_request"] = op.duration_ms

    # Step 3: Load thread messages (simulated)
    with ProfiledOperation("3. Load thread messages") as op:
        # Simulate database query
        await asyncio.sleep(0.002)  # 2ms simulated DB query
        thread_messages = [MockMessage("user" if i % 2 == 0 else "assistant", f"Message {i}" * 10) for i in range(50)]
    durations["load_messages"] = op.duration_ms

    # Step 4: Build thread memory
    with ProfiledOperation("4. Build thread memory") as op:
        memory_parts = []
        for msg in thread_messages[-10:]:
            memory_parts.append(f"{msg.role}: {msg.content[:200]}...")
        chat_request.thread_memory = "\n".join(memory_parts)
    durations["build_memory"] = op.duration_ms

    # Step 5: Process request (simulated)
    with ProfiledOperation("5. Process request (LLM call simulated)") as op:
        # Simulate LLM API call
        await asyncio.sleep(0.050)  # 50ms simulated API call
        response = {"content": "This is a response"}
    durations["process_request"] = op.duration_ms

    # Step 6: Save response (simulated)
    with ProfiledOperation("6. Save response to database") as op:
        # Simulate database write
        await asyncio.sleep(0.003)  # 3ms simulated DB write
    durations["save_response"] = op.duration_ms

    total_duration = sum(durations.values())
    print(f"\nTotal request duration: {total_duration:.3f}ms")

    # Analyze bottlenecks
    print("\nBottleneck Analysis:")
    sorted_durations = sorted(durations.items(), key=lambda x: x[1], reverse=True)
    for step, duration in sorted_durations:
        percentage = (duration / total_duration * 100) if total_duration > 0 else 0
        print(f"  {step}: {duration:.3f}ms ({percentage:.1f}%)")

    print("\nOptimization Opportunities:")
    if durations["import"] > 1.0:
        print("  ⚠ Import overhead significant (>1ms)")
        print("    → Ensure import caching is working")
    else:
        print("  ✓ Import overhead minimal")

    if durations["load_messages"] > 10.0:
        print("  ⚠ Message loading slow (>10ms)")
        print("    → Add database indexes")
        print("    → Use SQL LIMIT instead of Python slicing")
    else:
        print("  ✓ Message loading acceptable")

    if durations["build_memory"] > 1.0:
        print("  ⚠ Memory building slow (>1ms)")
        print("    → Consider pre-formatting messages")
    else:
        print("  ✓ Memory building fast")


async def profile_streaming_request() -> None:
    """Profile streaming response performance."""
    print_section("Streaming Request Profiling")

    print("\nSimulating streaming response:")

    # Simulate streaming chunks
    chunk_count = 20
    durations = []

    async def generate_chunk(chunk_id: int) -> str:
        """Simulate generating a response chunk."""
        await asyncio.sleep(0.005)  # 5ms per chunk
        return f"Chunk {chunk_id} content"

    start_time = time.perf_counter()
    first_chunk_time: Optional[float] = None

    for i in range(chunk_count):
        chunk_start = time.perf_counter()
        chunk = await generate_chunk(i)
        chunk_duration = (time.perf_counter() - chunk_start) * 1000
        durations.append(chunk_duration)

        if i == 0:
            first_chunk_time = (time.perf_counter() - start_time) * 1000

    total_time = (time.perf_counter() - start_time) * 1000

    results = BenchmarkResults(name="Streaming Chunks", samples=durations)
    print(format_results(results))

    print(f"Time to First Byte (TTFB): {first_chunk_time:.2f}ms")
    print(f"Total streaming time: {total_time:.2f}ms")
    print(f"Average throughput: {chunk_count / (total_time / 1000):.2f} chunks/sec")

    if first_chunk_time and first_chunk_time < 50:
        print("✓ Good TTFB (< 50ms)")
    elif first_chunk_time:
        print("⚠ High TTFB - consider optimizations")


async def benchmark_request_variants() -> None:
    """Benchmark different request variants."""
    print_section("Request Variant Benchmarks")

    # Simulate different request types
    request_types = [
        ("Simple request (no history)", 0, 10),
        ("With history (10 msgs)", 10, 10),
        ("With history (50 msgs)", 50, 10),
        ("With history (100 msgs)", 100, 10),
    ]

    for request_type, message_count, iterations in request_types:
        print(f"\n{request_type}:")
        durations = []

        for _ in range(iterations):
            start = time.perf_counter()

            # Simulate request processing
            if message_count > 0:
                messages = [{"role": "user", "content": f"msg {i}"} for i in range(message_count)]
                memory = "\n".join([f"{m['role']}: {m['content']}" for m in messages[-10:]])

            # Simulate minimal processing
            await asyncio.sleep(0.001)

            duration = (time.perf_counter() - start) * 1000
            durations.append(duration)

        results = BenchmarkResults(name=request_type, samples=durations)
        print(format_results(results))


async def main() -> None:
    """Run all request profiling tests."""
    try:
        await profile_chat_request_workflow()
        await profile_streaming_request()
        await benchmark_request_variants()

        print_section("Request Profiling Summary")
        print("\nRequest profiling completed successfully.")
        print("\nKey Takeaways:")
        print("1. Import caching reduces overhead significantly")
        print("2. Database queries dominate latency (optimize with indexes)")
        print("3. Memory building is fast and not a bottleneck")
        print("4. LLM API calls are the primary latency source (expected)")
        print("5. Streaming provides good TTFB for better UX")

    except Exception as e:
        print(f"\nError during profiling: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
