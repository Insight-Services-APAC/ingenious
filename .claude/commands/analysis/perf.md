# Performance Bottleneck Analysis

Perform deep analysis to identify performance bottlenecks across the codebase.

## When to Use

- When application is slow
- Before scaling or optimization work
- During performance review cycles

## Arguments

Usage: `/perf [target] [--focus area]`

- `target` - Directory or module to analyze (default: entire project)
- `--focus` - Specific area: database, api, frontend, backend, memory

If `$ARGUMENTS` is provided, use it as the target or focus area.

## Steps

### 1. Database and Query Performance

**Search for:**
- N+1 query patterns (loops containing database queries)
- Missing indexes on frequently queried columns
- `SELECT *` queries instead of specific columns
- Lack of query result caching
- Missing pagination on large result sets
- Synchronous database calls in loops
- Missing connection pooling

**Check:** ORM models, database queries, migration files

```bash
# Find potential N+1 patterns (Python)
grep -rn "for.*in.*:" --include="*.py" -A5 | grep -E "\.get\(|\.filter\(|\.query\("

# Find SELECT * (SQL files or raw queries)
grep -rn "SELECT \*" --include="*.py" --include="*.sql"
```

### 2. API and Network Performance

**Search for:**
- Sequential API calls that could be parallelized
- Missing request/response caching
- Large payloads without compression
- Synchronous external API calls blocking handlers
- Missing timeout configurations
- Repeated API calls for same data
- No rate limiting or circuit breakers

**Check:** API routes, HTTP clients, service layers

### 3. Frontend Performance

**Search for:**
- Large inline scripts/data in templates
- Missing lazy loading for images/components
- Excessive DOM manipulation in loops
- No debouncing/throttling on frequent events
- Large reactive data objects
- Missing code splitting
- Synchronous operations blocking UI
- Unnecessary re-renders

**Check:** Components, templates, event handlers

### 4. Backend Processing Performance

**Search for:**
- Synchronous processing of large datasets
- Missing async/await patterns
- Blocking I/O operations
- Inefficient loops (nested, repeated operations)
- Large file operations without streaming
- Missing worker queues for background tasks
- Heavy computation in request handlers
- No caching of expensive operations

**Check:** Service classes, background jobs, data processing

### 5. Memory and Resource Management

**Search for:**
- Memory leaks (unclosed connections, unreleased resources)
- Large objects kept in memory unnecessarily
- Missing context managers for file/connection handling
- Unbounded collections or caches
- Circular references preventing garbage collection
- Missing resource pooling
- Large log statements in hot paths

**Check:** Connection handling, cache implementations

### 6. Concurrency and Parallelization

**Search for:**
- Sequential operations that could run in parallel
- Missing async patterns for I/O-bound operations
- Thread-safety issues in shared resources
- Lock contention or deadlock risks
- Synchronous code in async contexts

**Check:** Batch operations, workflow orchestration

### 7. Analysis Approach

**Prioritize hot paths:**
1. User-facing request handlers
2. Background job processing
3. Database query-heavy operations
4. External API integrations

**Measure before optimizing:**
- Check for existing performance metrics/logging
- Identify actual bottlenecks vs perceived issues
- Look for TODO comments mentioning performance

### 8. Output Format

Provide actionable recommendations:

```markdown
## Performance Findings

### Critical (High Impact)
| Location | Issue | Impact | Fix |
|----------|-------|--------|-----|
| file:line | N+1 query in loop | 100+ queries per request | Use prefetch/eager loading |

### Important (Medium Impact)
...

### Minor (Low Impact)
...

## Recommended Actions
1. [Highest priority fix]
2. [Second priority fix]
...
```

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| Can't reproduce slowness | Environment difference | Profile in production-like setup |
| Too many findings | Large codebase | Focus on hot paths first |
| Unclear impact | No metrics | Add timing/profiling first |

## Success Criteria

- All performance hotspots identified
- Issues prioritized by impact
- Concrete fix recommendations provided
- Trade-offs documented (complexity vs speed)
