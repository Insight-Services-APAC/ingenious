"""Database connection pooling with support for SQLite and Azure SQL.

This module provides database-agnostic connection pooling with health checks,
retry logic, and automatic connection lifecycle management.
"""

import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from queue import Empty, Queue
from typing import Any, Iterator, Protocol

import pyodbc

from ingenious.core.structured_logging import get_logger

logger = get_logger(__name__)


class DatabaseConnection(Protocol):
    """Protocol defining the interface for database connections.

    This protocol ensures all database connection types provide a consistent
    interface for query execution, transaction management, and resource cleanup.
    """

    def execute(self, sql: str, params: Any = None) -> Any:
        """Execute a SQL query.

        Args:
            sql: SQL query string to execute.
            params: Optional query parameters.

        Returns:
            Query execution result.
        """
        ...

    def commit(self) -> None:
        """Commit the current transaction."""
        ...

    def close(self) -> None:
        """Close the database connection."""
        ...

    def cursor(self) -> Any:
        """Get a cursor for executing queries.

        Returns:
            Database cursor object.
        """
        ...


class ConnectionFactory(ABC):
    """Abstract factory for creating database connections.

    Subclasses implement database-specific connection creation and health checks.
    """

    @abstractmethod
    def create_connection(self) -> DatabaseConnection:
        """Create a new database connection.

        Returns:
            A new database connection instance.
        """
        pass

    @abstractmethod
    def is_connection_healthy(self, conn: DatabaseConnection) -> bool:
        """Check if a connection is healthy and usable.

        Args:
            conn: Database connection to check.

        Returns:
            True if the connection is healthy, False otherwise.
        """
        pass


class SQLiteConnectionFactory(ConnectionFactory):
    """Factory for creating SQLite connections.

    Configures SQLite connections with WAL mode, optimized cache settings,
    and row factory for dict-like row access.

    Attributes:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: str) -> None:
        """Initialize the SQLite connection factory.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = db_path

    def create_connection(self) -> sqlite3.Connection:
        """Create a new SQLite connection with optimized configuration.

        Configures the connection with:
        - WAL journal mode for better concurrency
        - Normal synchronous mode for performance
        - 10000 page cache size
        - Memory-based temp storage

        Returns:
            Configured SQLite connection with Row factory.
        """
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=30.0,
            isolation_level=None,  # autocommit mode
        )
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrency
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=10000")
        conn.execute("PRAGMA temp_store=MEMORY")
        return conn

    def is_connection_healthy(self, conn: DatabaseConnection) -> bool:
        """Check if a SQLite connection is healthy.

        Args:
            conn: SQLite connection to check.

        Returns:
            True if the connection can execute a simple query, False otherwise.
        """
        try:
            conn.execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False


class AzureSQLConnectionFactory(ConnectionFactory):
    """Factory for creating Azure SQL connections.

    Creates connections using pyodbc with autocommit enabled for
    compatibility with the connection pool pattern.

    Attributes:
        connection_string: ODBC connection string for Azure SQL.
    """

    def __init__(self, connection_string: str) -> None:
        """Initialize the Azure SQL connection factory.

        Args:
            connection_string: ODBC connection string for Azure SQL database.
        """
        self.connection_string = connection_string

    def create_connection(self) -> pyodbc.Connection:
        """Create a new Azure SQL connection with autocommit enabled.

        Returns:
            Configured pyodbc connection to Azure SQL.
        """
        conn = pyodbc.connect(self.connection_string)
        conn.autocommit = True
        return conn

    def is_connection_healthy(self, conn: pyodbc.Connection) -> bool:
        """Check if an Azure SQL connection is healthy.

        Args:
            conn: Azure SQL connection to check.

        Returns:
            True if the connection can execute a simple query, False otherwise.
        """
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception:
            return False


class ConnectionPool:
    """Database-agnostic connection pool with health checks and retry logic.

    Manages a pool of database connections with automatic health checking,
    retry logic for transient failures, and overflow capacity. Connections
    are pre-created and validated before use.

    Attributes:
        connection_factory: Factory for creating database connections.
        pool_size: Maximum number of connections to maintain in the pool.
        max_overflow: Maximum number of connections beyond pool_size.
        max_retries: Maximum number of retry attempts for connection operations.
        retry_delay: Initial delay in seconds between retry attempts (exponential backoff).
    """

    def __init__(
        self,
        connection_factory: ConnectionFactory,
        pool_size: int = 8,
        max_overflow: int = 16,
        max_retries: int = 3,
        retry_delay: float = 0.1,
    ) -> None:
        """Initialize the connection pool.

        Args:
            connection_factory: Factory for creating database connections.
            pool_size: Maximum number of connections in the pool. Defaults to 8.
            max_overflow: Maximum overflow connections beyond pool_size. Defaults to 16.
            max_retries: Maximum retry attempts for connection operations. Defaults to 3.
            retry_delay: Initial retry delay in seconds with exponential backoff. Defaults to 0.1.
        """
        self.connection_factory = connection_factory
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._pool: Queue[Any] = Queue(maxsize=pool_size)
        self._lock = threading.Lock()
        self._created_connections = 0

        # Pre-populate the pool
        self._initialize_pool()

    def _initialize_pool(self) -> None:
        """Initialize the connection pool with healthy connections.

        Creates and validates connections up to pool_size. If connection
        creation fails, connections will be created on-demand later.
        """
        for _ in range(self.pool_size):
            try:
                conn = self.connection_factory.create_connection()
                if self.connection_factory.is_connection_healthy(conn):
                    self._pool.put(conn)
                    self._created_connections += 1
                else:
                    conn.close()
            except Exception:
                # If we can't create initial connections, we'll create them on demand
                break

    @contextmanager
    def get_connection(self) -> Iterator[DatabaseConnection]:
        """Get a connection from the pool as a context manager.

        Retrieves a healthy connection from the pool, with automatic retry
        on failure. Returns the connection to the pool after use if still healthy,
        otherwise closes it. Supports overflow connections beyond pool_size.

        Yields:
            A healthy database connection.

        Raises:
            RuntimeError: If unable to get a connection after max_retries attempts.
        """
        conn = None
        retry_count = 0

        while retry_count <= self.max_retries:
            try:
                # Try to get a connection from the pool
                try:
                    conn = self._pool.get(timeout=5.0)
                except Empty:
                    # Pool is empty, create a new connection
                    with self._lock:
                        max_connections = self.pool_size + self.max_overflow
                        if self._created_connections < max_connections:
                            conn = self.connection_factory.create_connection()
                            self._created_connections += 1
                        else:
                            # Wait a bit and try again
                            time.sleep(self.retry_delay)
                            retry_count += 1
                            continue

                # Check if connection is healthy
                if conn and self.connection_factory.is_connection_healthy(conn):
                    try:
                        yield conn
                        # Return connection to pool if still healthy
                        if self.connection_factory.is_connection_healthy(conn):
                            self._pool.put_nowait(conn)
                        else:
                            conn.close()
                            with self._lock:
                                self._created_connections -= 1
                        return
                    except Exception as e:
                        # If there was an error using the connection, close it
                        if conn:
                            try:
                                conn.close()
                            except Exception:
                                pass
                            with self._lock:
                                self._created_connections -= 1
                        raise e
                else:
                    # Connection is unhealthy, close it and retry
                    if conn:
                        try:
                            conn.close()
                        except Exception:
                            pass
                        with self._lock:
                            self._created_connections -= 1

                    retry_count += 1
                    if retry_count <= self.max_retries:
                        time.sleep(self.retry_delay * retry_count)  # Exponential backoff

            except Exception as e:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    with self._lock:
                        self._created_connections -= 1

                retry_count += 1
                if retry_count <= self.max_retries:
                    time.sleep(self.retry_delay * retry_count)
                else:
                    raise RuntimeError(
                        f"Failed to get database connection after {self.max_retries} retries: {e}"
                    )

        raise RuntimeError(f"Failed to get database connection after {self.max_retries} retries")

    def close_all(self) -> None:
        """Close all connections in the pool.

        Drains the pool and closes all connections. Resets the connection
        counter to zero. Safe to call multiple times.
        """
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except (Empty, Exception):
                break

        with self._lock:
            self._created_connections = 0
