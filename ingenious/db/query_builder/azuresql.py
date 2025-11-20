"""Azure SQL (SQL Server) specific dialect implementation."""

from typing import Dict, List

from .base import Dialect


class AzureSQLDialect(Dialect):
    """Azure SQL (SQL Server) specific dialect implementation.

    Implements SQL Server syntax including MERGE for UPSERT, TOP for LIMIT,
    conditional table creation with sysobjects, and T-SQL data types.
    """

    def get_create_table_if_not_exists_prefix(self) -> str:
        """Get Azure SQL's conditional table creation prefix.

        Returns:
            SQL Server IF NOT EXISTS check using sysobjects with placeholder for table_name.
        """
        return "IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='{table_name}' AND xtype='U')\nCREATE TABLE"

    def get_limit_clause(self, limit: int) -> str:
        """Get Azure SQL's TOP clause for limiting results.

        Args:
            limit: Maximum number of rows to return.

        Returns:
            TOP clause in SQL Server format.
        """
        return f"TOP {limit}"

    def get_upsert_query(self, table: str, columns: List[str], conflict_column: str) -> str:
        """Generate Azure SQL MERGE statement for UPSERT.

        Args:
            table: Table name for the UPSERT operation.
            columns: List of column names to insert/update.
            conflict_column: Column name to check for conflicts.

        Returns:
            SQL Server MERGE statement for UPSERT operation.
        """
        columns_str = ", ".join(f"[{col}]" for col in columns)
        values_str = ", ".join("?" for _ in columns)
        updates_str = ", ".join(f"[{col}] = ?" for col in columns if col != conflict_column)

        # nosec B608: table name validated by caller, parameters use ? placeholders
        return f"""
            MERGE {table} AS target
            USING (SELECT ? as {conflict_column}) AS source ON target.[{conflict_column}] = source.{conflict_column}
            WHEN MATCHED THEN
                UPDATE SET {updates_str}
            WHEN NOT MATCHED THEN
                INSERT ({columns_str})
                VALUES ({values_str})
        """

    def get_temp_table_syntax(self, table_name: str, select_query: str) -> str:
        """Generate Azure SQL temporary table creation syntax.

        Args:
            table_name: Name for the temporary table (without # prefix).
            select_query: SELECT query to populate the temp table.

        Returns:
            SQL Server SELECT INTO #temp_table syntax.
        """
        # nosec B608: table name validated by caller, select_query is constructed internally
        return f"""
            {select_query}
            INTO #{table_name}
        """

    def get_drop_temp_table_syntax(self, table_name: str) -> str:
        """Generate Azure SQL temporary table drop syntax.

        Args:
            table_name: Name of the temporary table to drop (without # prefix).

        Returns:
            SQL Server DROP TABLE #temp_table query.
        """
        # nosec B608: table_name validated by caller
        return f"DROP TABLE #{table_name}"

    def get_data_types(self) -> Dict[str, str]:
        """Get Azure SQL data type mappings.

        Returns:
            Dictionary mapping generic types to SQL Server types.
        """
        return {
            "uuid": "UNIQUEIDENTIFIER",
            "varchar": "NVARCHAR(255)",
            "text": "NVARCHAR(MAX)",
            "boolean": "BIT",
            "datetime": "DATETIME2",
            "int": "INT",
            "json": "NVARCHAR(MAX)",
            "array": "NVARCHAR(MAX)",
        }

    def get_create_index_if_not_exists_syntax(
        self, index_name: str, table_name: str, columns: List[str]
    ) -> str:
        """Generate Azure SQL CREATE INDEX IF NOT EXISTS syntax.

        Args:
            index_name: Name for the index.
            table_name: Table to create the index on.
            columns: List of column names to include in the index.

        Returns:
            Azure SQL CREATE INDEX IF NOT EXISTS SQL using T-SQL conditional.
        """
        columns_str = ", ".join(f"[{col}]" for col in columns)
        # nosec B608: index_name, table_name, and columns are validated by caller
        return f"""IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = '{index_name}' AND object_id = OBJECT_ID('{table_name}'))
CREATE INDEX {index_name} ON {table_name}({columns_str})"""
