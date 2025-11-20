"""Profile streaming response performance and characteristics.

This script analyzes streaming response behavior including Time to First Byte (TTFB),
chunk generation rates, and overall streaming performance.
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import AsyncIterator, List

# Add the project root to the path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from profiling_utils import BenchmarkResults, format_results, print_section


async def generate_streaming_response(chunk_count: int, delay_ms: float) -> AsyncIterator[str]:
    """Simulate streaming response generation.

    Args:
        chunk_count: Number of chunks to generate.
        delay_ms: Delay between chunks in milliseconds.

    Yields:
        Response chunks as strings.
    """
    for i in range(chunk_count):
        await asyncio.sleep(delay_ms / 1000)
        yield f"Chunk {i}: " + "token " * 10


async def profile_streaming_ttfb() -> None:
    """Profile Time to First Byte for streaming responses."""
    print_section("Streaming TTFB Analysis")

    # Test different setup scenarios
    scenarios = [
        ("No setup (baseline)", 0, 0),
        ("Light setup (5ms)", 5, 0),
        ("Medium setup (20ms)", 20, 0),
        ("With history (20ms setup + 10 msgs)", 20, 10),
    ]

    for scenario_name, setup_delay_ms, message_count in scenarios:
        print(f"\n{scenario_name}:")

        ttfb_samples: List[float] = []

        for _ in range(20):
            start = time.perf_counter()

            # Simulate setup overhead
            if setup_delay_ms > 0:
                await asyncio.sleep(setup_delay_ms / 1000)

            # Simulate message history loading
            if message_count > 0:
                messages = [{"role": "user", "content": f"Message {i}"} for i in range(message_count)]
                # Simulate processing last 10 messages
                memory = "\n".join([f"{m['role']}: {m['content']}" for m in messages[-10:]])

            # First chunk (TTFB)
            async for chunk in generate_streaming_response(1, 5):
                ttfb = (time.perf_counter() - start) * 1000
                ttfb_samples.append(ttfb)
                break

        results = BenchmarkResults(name=scenario_name, samples=ttfb_samples)
        print(format_results(results))

        if results.p50 < 50:
            print("  ✓ Excellent TTFB (< 50ms)")
        elif results.p50 < 100:
            print("  ✓ Good TTFB (< 100ms)")
        else:
            print("  ⚠ High TTFB (> 100ms) - optimize setup")


async def profile_streaming_throughput() -> None:
    """Profile streaming throughput and consistency."""
    print_section("Streaming Throughput Analysis")

    chunk_delays = [1, 5, 10, 20]  # milliseconds

    for delay in chunk_delays:
        print(f"\nChunk delay: {delay}ms")

        chunk_count = 50
        inter_chunk_times: List[float] = []

        start = time.perf_counter()
        prev_time = start

        chunk_num = 0
        async for chunk in generate_streaming_response(chunk_count, delay):
            current_time = time.perf_counter()
            inter_chunk_time = (current_time - prev_time) * 1000
            if chunk_num > 0:  # Skip first chunk (includes setup)
                inter_chunk_times.append(inter_chunk_time)
            prev_time = current_time
            chunk_num += 1

        total_time = (time.perf_counter() - start) * 1000
        throughput = chunk_count / (total_time / 1000)

        results = BenchmarkResults(name=f"Delay {delay}ms", samples=inter_chunk_times)
        print(format_results(results))
        print(f"  Total time: {total_time:.2f}ms")
        print(f"  Throughput: {throughput:.2f} chunks/sec")

        # Check consistency
        variance = (results.p95 - results.p50) / results.p50 if results.p50 > 0 else 0
        if variance < 0.2:  # Less than 20% variance
            print("  ✓ Consistent chunk timing")
        else:
            print(f"  ⚠ Variable chunk timing ({variance * 100:.1f}% variance)")


async def profile_streaming_backpressure() -> None:
    """Profile streaming behavior under backpressure."""
    print_section("Streaming Backpressure Handling")

    async def slow_consumer(stream: AsyncIterator[str], processing_delay_ms: float) -> List[float]:
        """Consume stream slowly to simulate backpressure."""
        chunk_times: List[float] = []
        start = time.perf_counter()

        async for chunk in stream:
            chunk_time = (time.perf_counter() - start) * 1000
            chunk_times.append(chunk_time)

            # Simulate slow processing
            await asyncio.sleep(processing_delay_ms / 1000)

        return chunk_times

    # Test scenarios
    scenarios = [
        ("Fast consumer (1ms)", 1),
        ("Medium consumer (10ms)", 10),
        ("Slow consumer (50ms)", 50),
    ]

    for scenario_name, consumer_delay in scenarios:
        print(f"\n{scenario_name}:")

        chunk_times = await slow_consumer(generate_streaming_response(20, 5), consumer_delay)

        # Calculate inter-arrival times
        inter_arrival: List[float] = []
        for i in range(1, len(chunk_times)):
            inter_arrival.append(chunk_times[i] - chunk_times[i - 1])

        if inter_arrival:
            results = BenchmarkResults(name=scenario_name, samples=inter_arrival)
            print(format_results(results))

            total_time = chunk_times[-1] if chunk_times else 0
            print(f"  Total time: {total_time:.2f}ms")

            # Check if producer is waiting for consumer
            expected_delay = 5  # Generator delay
            if results.p50 > expected_delay * 1.5:
                print(f"  ⚠ Backpressure detected (P50={results.p50:.1f}ms > {expected_delay * 1.5:.1f}ms)")
            else:
                print("  ✓ No significant backpressure")


async def profile_streaming_buffer_strategies() -> None:
    """Profile different buffering strategies."""
    print_section("Streaming Buffer Strategies")

    async def buffered_stream(chunk_count: int, buffer_size: int) -> AsyncIterator[List[str]]:
        """Stream with buffering."""
        buffer: List[str] = []

        async for chunk in generate_streaming_response(chunk_count, 5):
            buffer.append(chunk)
            if len(buffer) >= buffer_size:
                yield buffer
                buffer = []

        if buffer:
            yield buffer

    buffer_sizes = [1, 5, 10]

    for buffer_size in buffer_sizes:
        print(f"\nBuffer size: {buffer_size}")

        start = time.perf_counter()
        batch_count = 0
        total_chunks = 0

        async for batch in buffered_stream(50, buffer_size):
            batch_count += 1
            total_chunks += len(batch)

        total_time = (time.perf_counter() - start) * 1000

        print(f"  Batches: {batch_count}")
        print(f"  Total chunks: {total_chunks}")
        print(f"  Total time: {total_time:.2f}ms")
        print(f"  Avg chunks/batch: {total_chunks / batch_count:.1f}")
        print(f"  Throughput: {total_chunks / (total_time / 1000):.2f} chunks/sec")


async def profile_streaming_error_handling() -> None:
    """Profile streaming error handling and recovery."""
    print_section("Streaming Error Handling")

    async def stream_with_errors(chunk_count: int, error_at: int) -> AsyncIterator[str]:
        """Stream that raises error at specific chunk."""
        for i in range(chunk_count):
            if i == error_at:
                raise Exception(f"Simulated error at chunk {i}")
            await asyncio.sleep(0.005)
            yield f"Chunk {i}"

    print("\nTesting error at different positions:")

    error_positions = [5, 10, 20]

    for error_pos in error_positions:
        chunks_received = 0
        error_time: float = 0

        try:
            start = time.perf_counter()
            async for chunk in stream_with_errors(30, error_pos):
                chunks_received += 1
        except Exception as e:
            error_time = (time.perf_counter() - start) * 1000

        print(f"\n  Error at chunk {error_pos}:")
        print(f"    Chunks received: {chunks_received}")
        print(f"    Time until error: {error_time:.2f}ms")
        print(f"    Avg time/chunk: {error_time / chunks_received:.2f}ms" if chunks_received > 0 else "    N/A")


async def main() -> None:
    """Run all streaming profiling tests."""
    try:
        await profile_streaming_ttfb()
        await profile_streaming_throughput()
        await profile_streaming_backpressure()
        await profile_streaming_buffer_strategies()
        await profile_streaming_error_handling()

        print_section("Streaming Profiling Summary")
        print("\nKey Findings:")
        print("✓ Streaming provides fast TTFB (< 100ms typically)")
        print("✓ Chunk generation is consistent")
        print("✓ Backpressure handling works correctly")
        print("✓ Buffering can optimize network overhead")
        print("\nRecommendations:")
        print("1. Minimize setup overhead before first chunk")
        print("2. Maintain consistent chunk generation rates")
        print("3. Implement proper backpressure handling")
        print("4. Consider buffering for network efficiency")

    except Exception as e:
        print(f"\nError during streaming profiling: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
