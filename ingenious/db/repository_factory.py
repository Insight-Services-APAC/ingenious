from typing import Any, Dict, List, Optional

from ingenious.config import IngeniousSettings
from ingenious.db.base_sql import BaseSQLRepository
from ingenious.db.chat_history_repository import IChatHistoryRepository
from ingenious.db.connection_pool import (
    AzureSQLConnectionFactory,
    ConnectionPool,
    SQLiteConnectionFactory,
)
from ingenious.db.query_builder import AzureSQLDialect, QueryBuilder, SQLiteDialect
from ingenious.models.database_client import DatabaseClientType


class RepositoryFactory:
    """Factory for creating database repository instances based on configuration."""

    @staticmethod
    def create_chat_history_repository(
        db_type: DatabaseClientType, config: IngeniousSettings
    ) -> IChatHistoryRepository:
        """Create a chat history repository based on database type."""

        if db_type == DatabaseClientType.SQLITE:
            return RepositoryFactory._create_sqlite_repository(config)
        elif db_type == DatabaseClientType.AZURESQL:
            return RepositoryFactory._create_azuresql_repository(config)
        elif db_type == DatabaseClientType.COSMOS:
            return RepositoryFactory._create_cosmos_repository(config)
        else:
            raise ValueError(f"Unsupported database type: {db_type}")

    @staticmethod
    def _create_sqlite_repository(config: IngeniousSettings) -> BaseSQLRepository:
        """Create SQLite repository with proper dependencies."""
        from ingenious.db.sqlite import sqlite_ChatHistoryRepository

        return sqlite_ChatHistoryRepository(config)

    @staticmethod
    def _create_azuresql_repository(config: IngeniousSettings) -> BaseSQLRepository:
        """Create Azure SQL repository with proper dependencies."""
        from ingenious.db.azuresql import azuresql_ChatHistoryRepository

        return azuresql_ChatHistoryRepository(config)

    @staticmethod
    def _create_cosmos_repository(config: IngeniousSettings) -> IChatHistoryRepository:
        """Create Cosmos DB repository with proper dependencies."""
        from ingenious.db.cosmos import cosmos_ChatHistoryRepository

        return cosmos_ChatHistoryRepository(config)


class ModernRepositoryFactory:
    """Modern factory that creates repositories using composition pattern directly."""

    @staticmethod
    def create_chat_history_repository(
        db_type: DatabaseClientType, config: IngeniousSettings
    ) -> IChatHistoryRepository:
        """Create a repository using composition pattern."""

        if db_type == DatabaseClientType.SQLITE:
            return ModernRepositoryFactory._create_sqlite_repository(config)
        elif db_type == DatabaseClientType.AZURESQL:
            return ModernRepositoryFactory._create_azuresql_repository(config)
        elif db_type == DatabaseClientType.COSMOS:
            return ModernRepositoryFactory._create_cosmos_repository(config)
        else:
            raise ValueError(f"Unsupported database type: {db_type}")

    @staticmethod
    def _create_sqlite_repository(
        config: IngeniousSettings,
    ) -> "SQLiteChatHistoryRepository":
        """Create SQLite repository using composition."""
        import os

        db_path = config.chat_history.database_path

        # Ensure directory exists
        db_dir_check = os.path.dirname(db_path)
        if not os.path.exists(db_dir_check):
            os.makedirs(db_dir_check)

        # Create dependencies
        connection_factory = SQLiteConnectionFactory(db_path)
        pool_size = getattr(config.chat_history, "connection_pool_size", 8)
        connection_pool = ConnectionPool(connection_factory, pool_size=pool_size)
        query_builder = QueryBuilder(SQLiteDialect())

        return SQLiteChatHistoryRepository(config, query_builder, connection_pool)

    @staticmethod
    def _create_azuresql_repository(
        config: IngeniousSettings,
    ) -> "AzureSQLChatHistoryRepository":
        """Create Azure SQL repository using composition."""
        connection_string = config.chat_history.database_connection_string
        if not connection_string:
            raise ValueError(
                "Azure SQL connection string is required for azuresql chat history repository"
            )

        # Create dependencies
        connection_factory = AzureSQLConnectionFactory(connection_string)
        pool_size = getattr(config.chat_history, "connection_pool_size", 8)
        connection_pool = ConnectionPool(connection_factory, pool_size=pool_size)
        query_builder = QueryBuilder(AzureSQLDialect())

        return AzureSQLChatHistoryRepository(config, query_builder, connection_pool)

    @staticmethod
    def _create_cosmos_repository(
        config: IngeniousSettings,
    ) -> IChatHistoryRepository:
        """Create Cosmos DB repository using composition."""
        from ingenious.db.cosmos import cosmos_ChatHistoryRepository

        return cosmos_ChatHistoryRepository(config)


class SQLiteChatHistoryRepository(BaseSQLRepository):
    """Modern SQLite repository using composition."""

    def __init__(
        self,
        config: IngeniousSettings,
        query_builder: QueryBuilder,
        connection_pool: ConnectionPool,
    ):
        self.pool = connection_pool
        super().__init__(config, query_builder)

    def __del__(self) -> None:
        """Destructor to ensure connections are properly closed."""
        try:
            self.close()
        except Exception:
            pass

    def close(self) -> None:
        """Close all connections in the pool."""
        if hasattr(self, "pool"):
            self.pool.close_all()

    def _init_connection(self) -> None:
        """Connection already initialized via connection pool."""
        pass

    def _execute_sql(
        self, sql: str, params: list[Any] | None = None, expect_results: bool = True
    ) -> Any:
        """Execute SQL using the connection pool."""
        if params is None:
            params = []

        try:
            with self.pool.get_connection() as connection:
                cursor = connection.cursor()

                if expect_results:
                    res = cursor.execute(sql, params)
                    rows = res.fetchall()
                    result = [dict(row) for row in rows]
                    return result
                else:
                    connection.execute(sql, params)
                    connection.commit()

        except Exception as e:
            from ingenious.errors import DatabaseQueryError

            raise DatabaseQueryError(
                "SQLite query execution failed",
                context={
                    "query_preview": sql[:100] + "..." if len(sql) > 100 else sql,
                    "param_count": len(params) if params else 0,
                    "expect_results": expect_results,
                },
                cause=e,
            ) from e

    async def get_threads_for_user(
        self, identifier: str, thread_id: Optional[str] = None
    ) -> Any:
        """Get threads for user - delegates to existing SQLite implementation."""
        # This would be implemented by copying the existing implementation
        # from the SQLite repository class
        pass

    async def update_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, object]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Update thread - delegates to existing SQLite implementation."""
        # This would be implemented by copying the existing implementation
        # from the SQLite repository class
        return ""


class AzureSQLChatHistoryRepository(BaseSQLRepository):
    """Modern Azure SQL repository using composition."""

    def __init__(
        self,
        config: IngeniousSettings,
        query_builder: QueryBuilder,
        connection_pool: ConnectionPool,
    ):
        self.pool = connection_pool
        super().__init__(config, query_builder)

    def _init_connection(self) -> None:
        """Connection already initialized via connection pool."""
        pass

    def _execute_sql(
        self, sql: str, params: list[Any] | None = None, expect_results: bool = True
    ) -> Any:
        """Execute SQL using the connection pool."""
        if params is None:
            params = []

        try:
            with self.pool.get_connection() as connection:
                cursor = connection.cursor()

                if expect_results:
                    cursor.execute(sql, params)
                    rows = cursor.fetchall()
                    # Convert to list of dictionaries
                    columns = [column[0] for column in cursor.description]
                    result = [dict(zip(columns, row)) for row in rows]
                    cursor.close()
                    return result
                else:
                    cursor.execute(sql, params)
                    connection.commit()
                    cursor.close()

        except Exception as e:
            from ingenious.errors import DatabaseQueryError

            raise DatabaseQueryError(
                "Azure SQL query execution failed",
                context={
                    "query_preview": sql[:100] + "..." if len(sql) > 100 else sql,
                    "param_count": len(params) if params else 0,
                    "expect_results": expect_results,
                },
                cause=e,
            ) from e

    async def get_threads_for_user(
        self, identifier: str, thread_id: Optional[str] = None
    ) -> Any:
        """Get threads for user - delegates to existing Azure SQL implementation."""
        # This would be implemented by copying the existing implementation
        # from the Azure SQL repository class
        pass

    async def update_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, object]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Update thread - delegates to existing Azure SQL implementation."""
        # This would be implemented by copying the existing implementation
        # from the Azure SQL repository class
        return ""
