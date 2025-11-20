"""Migration: Add performance indexes to chat_history table.

This migration adds indexes to optimize common query patterns:
- Thread messages by timestamp (most common query)
- User messages by timestamp (for exports/analytics)

Run this script to add indexes to existing SQLite databases.
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path


def create_indexes(cursor: sqlite3.Cursor) -> None:
    """Create performance indexes.

    Args:
        cursor: Database cursor for executing SQL.
    """
    print("Creating performance indexes...")

    # Index 1: Thread messages sorted by timestamp
    print("  Creating idx_messages_thread_timestamp...")
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_thread_timestamp 
        ON chat_history(thread_id, timestamp DESC)
    """)
    print("  ✓ Created idx_messages_thread_timestamp")

    # Index 2: User messages sorted by timestamp
    print("  Creating idx_messages_user_timestamp...")
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_user_timestamp 
        ON chat_history(user_id, timestamp DESC)
    """)
    print("  ✓ Created idx_messages_user_timestamp")

    # Index 3: Memory/summary table (if exists)
    print("  Checking for chat_history_summary table...")
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='chat_history_summary'
    """)
    if cursor.fetchone():
        print("  Creating idx_memory_thread_timestamp...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_thread_timestamp 
            ON chat_history_summary(thread_id, timestamp DESC)
        """)
        print("  ✓ Created idx_memory_thread_timestamp")
    else:
        print("  ℹ chat_history_summary table not found, skipping")


def verify_indexes(cursor: sqlite3.Cursor) -> None:
    """Verify that indexes were created successfully.

    Args:
        cursor: Database cursor for executing SQL.
    """
    print("\nVerifying indexes...")

    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='index' AND tbl_name='chat_history'
        ORDER BY name
    """)

    indexes = cursor.fetchall()
    print(f"  Found {len(indexes)} indexes on chat_history:")
    for idx in indexes:
        print(f"    - {idx[0]}")


def analyze_query_plan(cursor: sqlite3.Cursor) -> None:
    """Analyze query plan to verify index usage.

    Args:
        cursor: Database cursor for executing SQL.
    """
    print("\nAnalyzing query plan for thread message query...")

    cursor.execute("""
        EXPLAIN QUERY PLAN
        SELECT * FROM chat_history 
        WHERE thread_id = 'test' 
        ORDER BY timestamp DESC 
        LIMIT 10
    """)

    print("  Query plan:")
    for row in cursor.fetchall():
        # Row format: (id, parent, notused, detail)
        print(f"    {row[3]}")

    # Check if index is being used
    cursor.execute("""
        EXPLAIN QUERY PLAN
        SELECT * FROM chat_history 
        WHERE thread_id = 'test' 
        ORDER BY timestamp DESC 
        LIMIT 10
    """)

    plan = " ".join([str(row[3]) for row in cursor.fetchall()])
    if "idx_messages_thread_timestamp" in plan:
        print("  ✓ Index is being used")
    else:
        print("  ⚠ Index may not be optimal")


def optimize_database(cursor: sqlite3.Cursor) -> None:
    """Optimize database after adding indexes.

    Args:
        cursor: Database cursor for executing SQL.
    """
    print("\nOptimizing database...")

    print("  Running ANALYZE...")
    cursor.execute("ANALYZE")
    print("  ✓ Statistics updated")

    # Note: VACUUM can take a long time on large databases
    # and locks the database, so we make it optional
    print("  ℹ Run 'VACUUM' manually if needed to reclaim space")


def get_database_stats(cursor: sqlite3.Cursor) -> None:
    """Display database statistics.

    Args:
        cursor: Database cursor for executing SQL.
    """
    print("\nDatabase statistics:")

    # Message count
    cursor.execute("SELECT COUNT(*) FROM chat_history")
    message_count = cursor.fetchone()[0]
    print(f"  Messages: {message_count:,}")

    # Thread count
    cursor.execute("SELECT COUNT(DISTINCT thread_id) FROM chat_history")
    thread_count = cursor.fetchone()[0]
    print(f"  Threads: {thread_count:,}")

    # Database size
    cursor.execute("SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()")
    db_size = cursor.fetchone()[0]
    print(f"  Database size: {db_size / 1024 / 1024:.2f} MB")


def migrate(db_path: str, dry_run: bool = False) -> None:
    """Run migration to add performance indexes.

    Args:
        db_path: Path to SQLite database file.
        dry_run: If True, show what would be done without making changes.
    """
    if not os.path.exists(db_path):
        print(f"✗ Database not found: {db_path}")
        sys.exit(1)

    print(f"Database: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Show current state
        get_database_stats(cursor)

        if dry_run:
            print("\n[DRY RUN] Would create the following indexes:")
            print("  - idx_messages_thread_timestamp")
            print("  - idx_messages_user_timestamp")
            print("  - idx_memory_thread_timestamp (if summary table exists)")
            return

        # Create indexes
        create_indexes(cursor)
        conn.commit()

        # Verify
        verify_indexes(cursor)

        # Analyze query plan
        analyze_query_plan(cursor)

        # Optimize
        optimize_database(cursor)
        conn.commit()

        print("\n✓ Migration completed successfully")

    except Exception as e:
        conn.rollback()
        print(f"\n✗ Migration failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


def main() -> None:
    """Main entry point for migration script."""
    parser = argparse.ArgumentParser(
        description="Add performance indexes to Ingenious chat history database"
    )
    parser.add_argument(
        "database",
        nargs="?",
        default=os.path.expanduser("~/.ingenious/chat_history.db"),
        help="Path to SQLite database (default: ~/.ingenious/chat_history.db)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("  Ingenious Performance Index Migration")
    print("=" * 60)
    print()

    migrate(args.database, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
