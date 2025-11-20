# Database Indexes for Performance Optimization

This document describes the recommended database indexes for optimal query performance in Ingenious.

## Overview

Database indexes are crucial for fast query execution, especially when filtering and sorting by specific columns. The following indexes are recommended based on common query patterns.

## Recommended Indexes

### 1. Messages by Thread and Timestamp

**Purpose:** Optimize `get_thread_messages()` queries that retrieve recent messages for a thread.

**SQLite:**
```sql
-- Create index on thread_id and timestamp for efficient message retrieval
CREATE INDEX IF NOT EXISTS idx_messages_thread_timestamp 
    ON chat_history(thread_id, timestamp DESC);
```

**Azure SQL:**
```sql
-- Create index on thread_id and timestamp for efficient message retrieval
CREATE NONCLUSTERED INDEX idx_messages_thread_timestamp 
    ON chat_history(thread_id, timestamp DESC)
    INCLUDE (user_id, message_id, role, content, positive_feedback, 
             content_filter_results, tool_calls, tool_call_id, tool_call_function);
```

**Impact:**
- **Before:** Full table scan or index scan without timestamp ordering
- **After:** Index seek directly to thread messages, pre-sorted
- **Expected improvement:** 50-90% reduction in query time for large histories

### 2. Thread Lookup Index

**Purpose:** Fast thread existence checks and thread metadata retrieval.

**SQLite:**
```sql
-- Index for fast thread lookups
CREATE INDEX IF NOT EXISTS idx_threads_id 
    ON threads(id);
```

**Azure SQL:**
```sql
-- Index for fast thread lookups
CREATE NONCLUSTERED INDEX idx_threads_id 
    ON threads(id);
```

### 3. User Messages Index

**Purpose:** Fast retrieval of all messages for a user (for analytics, exports, etc.).

**SQLite:**
```sql
-- Index for user message queries
CREATE INDEX IF NOT EXISTS idx_messages_user_timestamp 
    ON chat_history(user_id, timestamp DESC);
```

**Azure SQL:**
```sql
-- Index for user message queries
CREATE NONCLUSTERED INDEX idx_messages_user_timestamp 
    ON chat_history(user_id, timestamp DESC);
```

### 4. Memory Summary Index (if using memory table)

**Purpose:** Fast retrieval of thread memory/summary.

**SQLite:**
```sql
-- Index for memory lookups
CREATE INDEX IF NOT EXISTS idx_memory_thread_timestamp 
    ON chat_history_summary(thread_id, timestamp DESC);
```

**Azure SQL:**
```sql
-- Index for memory lookups
CREATE NONCLUSTERED INDEX idx_memory_thread_timestamp 
    ON chat_history_summary(thread_id, timestamp DESC);
```

## Cosmos DB Indexing

For Cosmos DB, indexing is configured in the container's indexing policy.

**Recommended Indexing Policy:**
```json
{
  "indexingMode": "consistent",
  "automatic": true,
  "includedPaths": [
    {
      "path": "/*"
    }
  ],
  "excludedPaths": [
    {
      "path": "/content/*"
    },
    {
      "path": "/_etag/?"
    }
  ],
  "compositeIndexes": [
    [
      {
        "path": "/thread_id",
        "order": "ascending"
      },
      {
        "path": "/timestamp",
        "order": "descending"
      }
    ],
    [
      {
        "path": "/user_id",
        "order": "ascending"
      },
      {
        "path": "/timestamp",
        "order": "descending"
      }
    ]
  ]
}
```

**Notes:**
- Exclude large content fields from indexing to save RU costs
- Use composite indexes for multi-field queries
- Monitor RU consumption and adjust as needed

## Migration Script

For SQLite databases, you can run the following migration:

```python
"""Migration: Add performance indexes to chat_history table."""

import sqlite3
import os

def migrate(db_path: str) -> None:
    """Add performance indexes to database.
    
    Args:
        db_path: Path to SQLite database file.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Index for thread messages
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_thread_timestamp 
            ON chat_history(thread_id, timestamp DESC)
        """)
        
        # Index for user messages
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_user_timestamp 
            ON chat_history(user_id, timestamp DESC)
        """)
        
        conn.commit()
        print("✓ Indexes created successfully")
        
        # Analyze query plan
        cursor.execute("""
            EXPLAIN QUERY PLAN
            SELECT * FROM chat_history 
            WHERE thread_id = 'test' 
            ORDER BY timestamp DESC 
            LIMIT 10
        """)
        
        print("\nQuery plan after indexing:")
        for row in cursor.fetchall():
            print(f"  {row}")
            
    except Exception as e:
        conn.rollback()
        print(f"✗ Error creating indexes: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    # Default database path
    db_path = os.path.expanduser("~/.ingenious/chat_history.db")
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        print("Please provide the correct database path.")
    else:
        migrate(db_path)
```

Save this as `scripts/migrations/add_performance_indexes.py` and run:

```bash
python scripts/migrations/add_performance_indexes.py
```

## Verifying Index Usage

### SQLite

Check if indexes are being used:

```sql
-- Check existing indexes
.indexes chat_history

-- Explain query plan
EXPLAIN QUERY PLAN
SELECT * FROM chat_history 
WHERE thread_id = '123' 
ORDER BY timestamp DESC 
LIMIT 10;
```

Expected output should show "SEARCH chat_history USING INDEX idx_messages_thread_timestamp".

### Azure SQL

Check index usage:

```sql
-- Check existing indexes
SELECT 
    i.name AS index_name,
    i.type_desc,
    ds.index_usage_stats
FROM sys.indexes i
JOIN sys.dm_db_index_usage_stats ds 
    ON i.object_id = ds.object_id AND i.index_id = ds.index_id
WHERE OBJECT_NAME(i.object_id) = 'chat_history';

-- View execution plan
SET SHOWPLAN_TEXT ON;
GO
SELECT TOP 10 * 
FROM chat_history 
WHERE thread_id = '123' 
ORDER BY timestamp DESC;
GO
SET SHOWPLAN_TEXT OFF;
GO
```

### Cosmos DB

Monitor index usage through Azure Portal:
1. Navigate to your Cosmos DB account
2. Select "Metrics"
3. Check "Index Usage" metrics
4. Monitor RU consumption for queries

## Performance Testing

Before and after adding indexes, measure query performance:

```python
import time
import asyncio

async def benchmark_query():
    """Benchmark message retrieval query."""
    
    # Warm up
    for _ in range(5):
        await repository.get_thread_messages("test-thread", limit=10)
    
    # Measure
    durations = []
    for _ in range(100):
        start = time.perf_counter()
        await repository.get_thread_messages("test-thread", limit=10)
        duration = (time.perf_counter() - start) * 1000
        durations.append(duration)
    
    print(f"p50: {sorted(durations)[50]:.2f}ms")
    print(f"p95: {sorted(durations)[95]:.2f}ms")

asyncio.run(benchmark_query())
```

**Expected Results:**
- **Before indexes:** 10-50ms depending on table size
- **After indexes:** 2-5ms consistently

## Maintenance

### Analyze and Vacuum (SQLite)

Periodically optimize database:

```sql
-- Analyze query optimizer statistics
ANALYZE;

-- Reclaim unused space and defragment
VACUUM;
```

### Update Statistics (Azure SQL)

Keep statistics current:

```sql
-- Update statistics for chat_history table
UPDATE STATISTICS chat_history WITH FULLSCAN;
```

### Monitor Index Size

Track index overhead:

**SQLite:**
```sql
-- Check database size
SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size();
```

**Azure SQL:**
```sql
-- Check index size
SELECT 
    i.name,
    SUM(s.used_page_count) * 8 AS IndexSizeKB
FROM sys.indexes i
JOIN sys.dm_db_partition_stats s 
    ON i.object_id = s.object_id AND i.index_id = s.index_id
WHERE OBJECT_NAME(i.object_id) = 'chat_history'
GROUP BY i.name;
```

## Trade-offs

### Benefits
- ✓ 50-90% faster query execution
- ✓ Reduced CPU usage
- ✓ Better scalability
- ✓ Consistent performance with large datasets

### Costs
- ⚠ Additional disk space (typically 10-20% of table size per index)
- ⚠ Slightly slower writes (index maintenance overhead)
- ⚠ Memory usage for index cache

**Conclusion:** The performance benefits far outweigh the costs for read-heavy workloads like chat applications.

## See Also

- [Performance Baseline Document](baseline.md)
- [Query Optimization Best Practices](https://use-the-index-luke.com/)
- [SQLite Query Optimization](https://www.sqlite.org/queryplanner.html)
- [Azure SQL Index Design](https://docs.microsoft.com/en-us/sql/relational-databases/indexes/)
