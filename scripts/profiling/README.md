# Performance Profiling Scripts

This directory contains scripts for profiling and benchmarking the Ingenious application to identify performance bottlenecks and establish performance baselines.

## Prerequisites

Install profiling dependencies:

```bash
uv add --dev py-spy memory-profiler line-profiler psutil
```

## Available Scripts

### 1. `profile_imports.py`

Measures dynamic import performance and caching effectiveness.

**Usage:**
```bash
python scripts/profiling/profile_imports.py
```

**What it measures:**
- Cold vs warm cache import times
- Import caching effectiveness
- Overhead compared to standard imports
- Cache statistics

**Expected results:**
- Warm cache imports should be < 0.1ms
- Cache should provide 10x+ speedup

### 2. `profile_message_history.py`

Profiles message history loading and memory building operations.

**Usage:**
```bash
python scripts/profiling/profile_message_history.py
```

**What it measures:**
- Message loading with different history sizes
- Python slicing vs database query performance
- Memory building performance
- Different memory building strategies

**Expected results:**
- Memory building should be < 1ms
- Database queries are the bottleneck (1-10ms)

### 3. `profile_request.py`

Profiles complete chat request workflows.

**Usage:**
```bash
python scripts/profiling/profile_request.py
```

**What it measures:**
- End-to-end request processing time
- Individual step durations (import, load, process, save)
- Bottleneck identification
- Request variants (with/without history)

**Expected results:**
- Import overhead < 1ms (cached)
- Database operations: 2-10ms
- LLM calls dominate latency (50-500ms)

### 4. `profile_streaming.py`

Analyzes streaming response performance characteristics.

**Usage:**
```bash
python scripts/profiling/profile_streaming.py
```

**What it measures:**
- Time to First Byte (TTFB)
- Chunk generation throughput
- Streaming consistency
- Backpressure handling
- Buffer strategies

**Expected results:**
- TTFB < 100ms
- Consistent chunk timing
- Proper backpressure handling

### 5. `load_test.py`

Basic load testing to measure performance under concurrent requests.

**Usage:**
```bash
python scripts/profiling/load_test.py
```

**What it measures:**
- Sequential vs concurrent performance
- Import caching under load
- Memory usage under load
- Performance degradation at scale

**Expected results:**
- Linear scaling up to 25 concurrent requests
- Stable memory usage
- Consistent response times

### 6. `memory_profile.py`

Memory profiling to detect leaks and analyze memory usage patterns.

**Usage:**
```bash
python scripts/profiling/memory_profile.py
```

**What it measures:**
- Import cache memory footprint
- Message list memory usage
- Memory leak detection
- Memory growth over iterations

**Expected results:**
- Import cache < 10MB
- No memory leaks over repeated operations
- Stable memory after GC

## Shared Utilities

### `profiling_utils.py`

Common utilities used by all profiling scripts:

- `ProfileResult`: Container for profiling results
- `BenchmarkResults`: Statistical analysis of benchmark samples
- `time_function()`: Decorator for timing functions
- `format_results()`: Pretty-print benchmark results
- `print_section()`: Format section headers

## Running All Profiles

To run all profiling scripts and collect comprehensive baseline data:

```bash
# Run each script individually
python scripts/profiling/profile_imports.py > results/imports.txt
python scripts/profiling/profile_message_history.py > results/messages.txt
python scripts/profiling/profile_request.py > results/requests.txt
python scripts/profiling/profile_streaming.py > results/streaming.txt
python scripts/profiling/load_test.py > results/load.txt
python scripts/profiling/memory_profile.py > results/memory.txt
```

Or create a simple runner script:

```bash
#!/bin/bash
mkdir -p results
for script in profile_*.py load_test.py memory_profile.py; do
    echo "Running $script..."
    python "scripts/profiling/$script" > "results/$(basename $script .py).txt"
done
echo "All profiling complete. Results in results/"
```

## Interpreting Results

### Performance Metrics

- **p50 (median)**: Typical performance - 50% of requests are faster
- **p95**: 95th percentile - only 5% of requests are slower
- **p99**: 99th percentile - worst-case performance for most users
- **mean**: Average performance across all samples

### What to Look For

1. **High p95/p50 ratio (> 2x)**: High variance, inconsistent performance
2. **Slow operations (> 10ms)**: Potential bottlenecks
3. **Memory leaks**: Steady growth over iterations
4. **Cache effectiveness**: Cold vs warm cache speedup

### Common Bottlenecks

1. **Database queries**: Optimize with indexes, use LIMIT in SQL
2. **Dynamic imports**: Ensure caching is working (should be < 0.1ms)
3. **Message history**: Load only what's needed (last N messages)
4. **Memory building**: Should be fast (< 1ms), not a bottleneck
5. **LLM API calls**: Expected bottleneck (50-500ms), use streaming

## Advanced Profiling

### Using py-spy

For production profiling with minimal overhead:

```bash
# Profile a running process
py-spy top --pid <pid>

# Generate flame graph
py-spy record -o profile.svg -- python your_script.py
```

### Using line_profiler

For line-by-line profiling:

```python
from line_profiler import LineProfiler

profiler = LineProfiler()
profiler.add_function(your_function)
profiler.enable()
your_function()
profiler.disable()
profiler.print_stats()
```

### Using memory_profiler

For detailed memory profiling:

```bash
python -m memory_profiler your_script.py
```

## Contributing

When adding new profiling scripts:

1. Use `profiling_utils.py` for common functionality
2. Include clear section headers with `print_section()`
3. Provide both raw metrics and analysis
4. Include recommendations based on results
5. Update this README with usage instructions

## See Also

- [Performance Baseline Document](../../docs/performance/baseline.md)
- [Optimization Guidelines](../../docs/performance/optimization.md)
