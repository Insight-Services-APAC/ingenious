"""SQLite-specific SQL dialect implementation."""

from typing import Dict, List

from .base import Dialect


class SQLiteDialect(Dialect):
    """SQLite-specific SQL dialect implementation.

    Implements SQLite syntax for table creation, UPSERT with ON CONFLICT,
    temporary tables, and data type mappings.
    """

    def get_create_table_if_not_exists_prefix(self) -> str:
        """Get SQLite's CREATE TABLE IF NOT EXISTS prefix.

        Returns:
            The string 'CREATE TABLE IF NOT EXISTS'.
        """
        return "CREATE TABLE IF NOT EXISTS"

    def get_limit_clause(self, limit: int) -> str:
        """Get SQLite's LIMIT clause.

        Args:
            limit: Maximum number of rows to return.

        Returns:
            LIMIT clause in SQLite format.
        """
        return f"LIMIT {limit}"

    def get_upsert_query(self, table: str, columns: List[str], conflict_column: str) -> str:
        """Generate SQLite UPSERT query using ON CONFLICT.

        Args:
            table: Table name for the UPSERT operation.
            columns: List of column names to insert/update.
            conflict_column: Column name to check for conflicts.

        Returns:
            SQLite UPSERT query using ON CONFLICT DO UPDATE syntax.
        """
        columns_str = ", ".join(f'"{col}"' for col in columns)
        values_str = ", ".join("?" for _ in columns)
        updates_str = ", ".join(
            f'"{col}" = EXCLUDED."{col}"' for col in columns if col != conflict_column
        )

        # nosec B608: table name validated by caller, parameters use ? placeholders
        return f"""
            INSERT INTO {table} ({columns_str})
            VALUES ({values_str})
            ON CONFLICT ("{conflict_column}") DO UPDATE
            SET {updates_str}
        """

    def get_temp_table_syntax(self, table_name: str, select_query: str) -> str:
        """Generate SQLite temporary table creation syntax.

        Args:
            table_name: Name for the temporary table.
            select_query: SELECT query to populate the temp table.

        Returns:
            SQLite CREATE TEMP TABLE AS query.
        """
        # nosec B608: table_name validated by caller, select_query constructed internally
        return f"""
            CREATE TEMP TABLE {table_name} AS
            {select_query}
        """

    def get_drop_temp_table_syntax(self, table_name: str) -> str:
        """Generate SQLite temporary table drop syntax.

        Args:
            table_name: Name of the temporary table to drop.

        Returns:
            SQLite DROP TABLE query.
        """
        # nosec B608: table_name validated by caller
        return f"DROP TABLE {table_name}"

    def get_data_types(self) -> Dict[str, str]:
        """Get SQLite data type mappings.

        Returns:
            Dictionary mapping generic types to SQLite types.
        """
        return {
            "uuid": "UUID",
            "varchar": "TEXT",
            "text": "TEXT",
            "boolean": "BOOLEAN",
            "datetime": "TEXT",
            "int": "INT",
            "json": "JSONB",
            "array": "TEXT[]",
        }

    def get_create_index_syntax(
        self, index_name: str, table_name: str, column_name: str
    ) -> str:
        """Get SQLite index creation syntax.

        Args:
            index_name: Name for the index.
            table_name: Table to create index on.
            column_name: Column to index.

        Returns:
            SQLite CREATE INDEX IF NOT EXISTS statement.
        """
        # nosec B608: index_name, table_name, and column_name are validated by caller
        return f'CREATE INDEX IF NOT EXISTS "{index_name}" ON {table_name} ("{column_name}")'
