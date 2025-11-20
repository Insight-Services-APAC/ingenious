"""Abstract base class for database-specific SQL dialects."""

from abc import ABC, abstractmethod
from typing import Dict, List


class Dialect(ABC):
    """Abstract base class for database-specific SQL dialects.

    Subclasses implement database-specific SQL syntax for common operations
    including table creation, UPSERT, LIMIT clauses, and data types.
    """

    @abstractmethod
    def get_create_table_if_not_exists_prefix(self) -> str:
        """Get the CREATE TABLE IF NOT EXISTS prefix for this database.

        Returns:
            Database-specific SQL prefix for conditional table creation.
        """
        pass

    @abstractmethod
    def get_limit_clause(self, limit: int) -> str:
        """Get the LIMIT clause syntax for this database.

        Args:
            limit: Maximum number of rows to return.

        Returns:
            Database-specific LIMIT clause.
        """
        pass

    @abstractmethod
    def get_upsert_query(self, table: str, columns: List[str], conflict_column: str) -> str:
        """Generate database-specific UPSERT query.

        Args:
            table: Table name for the UPSERT operation.
            columns: List of column names to insert/update.
            conflict_column: Column name to check for conflicts.

        Returns:
            Database-specific UPSERT SQL query.
        """
        pass

    @abstractmethod
    def get_temp_table_syntax(self, table_name: str, select_query: str) -> str:
        """Get temporary table creation syntax for this database.

        Args:
            table_name: Name for the temporary table.
            select_query: SELECT query to populate the temp table.

        Returns:
            Database-specific temporary table creation SQL.
        """
        pass

    @abstractmethod
    def get_drop_temp_table_syntax(self, table_name: str) -> str:
        """Get temporary table drop syntax for this database.

        Args:
            table_name: Name of the temporary table to drop.

        Returns:
            Database-specific temporary table drop SQL.
        """
        pass

    @abstractmethod
    def get_data_types(self) -> Dict[str, str]:
        """Get mapping of generic to database-specific data types.

        Returns:
            Dictionary mapping generic type names to database-specific types.
        """
        pass

    @abstractmethod
    def get_create_index_syntax(
        self, index_name: str, table_name: str, column_name: str
    ) -> str:
        """Get index creation syntax for this database.

        Args:
            index_name: Name for the index.
            table_name: Table to create index on.
            column_name: Column to index.

        Returns:
            Database-specific CREATE INDEX SQL statement.
        """
        pass
