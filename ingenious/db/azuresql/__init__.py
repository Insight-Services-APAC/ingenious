import json
from typing import Any, Dict, List, Optional

import pyodbc

from ingenious.config import IngeniousSettings

# Future import placeholders for advanced error handling
# from ingenious.core.error_handling import (
#     database_operation,
#     operation_context,
#     with_correlation_id,
# )
from ingenious.core.structured_logging import get_logger
from ingenious.db.base_sql import BaseSQLRepository
from ingenious.db.chat_history_repository import IChatHistoryRepository
from ingenious.db.query_builder import AzureSQLDialect, QueryBuilder
from ingenious.errors import (
    DatabaseQueryError,
)

logger = get_logger(__name__)


class azuresql_ChatHistoryRepository(BaseSQLRepository):
    def __init__(self, config: IngeniousSettings) -> None:
        # Try to get connection string from azure_sql_services first, then fallback to chat_history
        self.connection_string = None
        if (
            config.azure_sql_services
            and config.azure_sql_services.database_connection_string
        ):
            self.connection_string = (
                config.azure_sql_services.database_connection_string
            )
        elif config.chat_history.database_connection_string:
            self.connection_string = config.chat_history.database_connection_string

        if not self.connection_string:
            raise ValueError(
                "Azure SQL connection string is required for azuresql chat history repository. "
                "Please set either INGENIOUS_AZURE_SQL_SERVICES__CONNECTION_STRING or "
                "INGENIOUS_CHAT_HISTORY__DATABASE_CONNECTION_STRING"
            )

        # Initialize query builder with Azure SQL dialect
        query_builder = QueryBuilder(AzureSQLDialect())

        # Call parent constructor which will call _init_connection and _create_tables
        super().__init__(config, query_builder)

    def _init_connection(self) -> None:
        """Initialize Azure SQL connection with retry logic."""
        import time

        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                logger.info(
                    f"Attempting Azure SQL connection (attempt {attempt + 1}/{max_retries})"
                )
                self.connection = pyodbc.connect(self.connection_string)
                self.connection.autocommit = True
                logger.info("Azure SQL connection established successfully")
                return
            except Exception as e:
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    logger.error("All connection attempts failed")
                    raise

    def _execute_sql(
        self, sql: str, params: list[Any] | None = None, expect_results: bool = True
    ) -> Any:
        """Execute SQL with Azure SQL connection handling."""
        if params is None:
            params = []
        cursor = None
        try:
            cursor = self.connection.cursor()

            if expect_results:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                # Convert to list of dictionaries
                columns = [column[0] for column in cursor.description]
                result = [dict(zip(columns, row)) for row in rows]
                return result
            else:
                cursor.execute(sql, params)
                self.connection.commit()

        except Exception as e:
            logger.error(
                "SQL execution failed",
                error=str(e),
                sql_query=sql[:100] + "..." if len(sql) > 100 else sql,
                param_count=len(params) if params else 0,
                operation="sql_execute",
            )
            raise DatabaseQueryError(
                "SQL query execution failed",
                context={
                    "query_preview": sql[:100] + "..." if len(sql) > 100 else sql,
                    "param_count": len(params) if params else 0,
                    "expect_results": expect_results,
                },
                cause=e,
            ) from e

        finally:
            if cursor:
                cursor.close()

    def execute_sql(
        self, sql: str, params: list[Any] | None = None, expect_results: bool = True
    ) -> Any:
        """Legacy method for backward compatibility."""
        if params is None:
            params = []
        return self._execute_sql(sql, params, expect_results)

    # Removed empty _create_tables override - using base class implementation

    async def _get_user_by_id(self, user_id: str) -> IChatHistoryRepository.User | None:
        cursor = self.connection.cursor()
        cursor.execute(
            """SELECT id, identifier, metadata, createdAt FROM users WHERE id = ?""",
            (user_id,),
        )
        row = cursor.fetchone()
        cursor.close()

        if row:
            return IChatHistoryRepository.User(
                id=row[0], identifier=row[1], metadata=row[2], createdAt=row[3]
            )
        return None

    async def get_threads_for_user(
        self, identifier: str, thread_id: Optional[str]
    ) -> Optional[List[IChatHistoryRepository.ThreadDict]]:
        # This is a simplified implementation
        # In a full implementation, you'd join with threads table and return proper thread data
        return []

    async def add_step(self, step_dict: IChatHistoryRepository.StepDict) -> None:
        logger.info(
            "Creating step in database",
            step_id=step_dict.get("id"),
            step_type=step_dict.get("type"),
            thread_id=step_dict.get("threadId"),
            operation="create_step",
        )

        # If disableFeedback is not provided, default to False
        step_dict["disableFeedback"] = step_dict.get("disableFeedback", False)

        step_dict["showInput"] = (
            str(step_dict.get("showInput", "")).lower()
            if "showInput" in step_dict
            else None
        )
        parameters = {
            key: value
            for key, value in step_dict.items()
            if value is not None and not (isinstance(value, dict) and not value)
        }
        parameters["metadata"] = json.dumps(step_dict.get("metadata", {}))
        parameters["generation"] = json.dumps(step_dict.get("generation", {}))

        columns = ", ".join(f"[{key}]" for key in parameters.keys())
        values = ", ".join("?" for key in parameters.keys())
        # nosec B608: table name 'steps' is hardcoded constant, parameters use ? placeholders
        query = f"""
            INSERT INTO steps ({columns})
            VALUES ({values});
        """
        self.execute_sql(
            sql=query, params=list(parameters.values()), expect_results=False
        )

    async def update_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, object]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        logger.info(
            "Updating thread",
            thread_id=thread_id,
            user_id=user_id,
            has_name=name is not None,
            has_metadata=metadata is not None,
            operation="update_thread",
        )
        user_identifier = None
        if user_id:
            logger.debug(
                "Retrieving user identifier",
                user_id=user_id,
                operation="get_user_identifier",
            )
            user = await self._get_user_by_id(user_id)
            if user:
                user_identifier = user.identifier

        data = {
            "id": thread_id,
            "createdAt": (self.get_now() if metadata is None else None),
            "name": (
                name
                if name is not None
                else (metadata.get("name") if metadata and "name" in metadata else None)
            ),
            "userId": user_id,
            "userIdentifier": user_identifier,
            "tags": json.dumps(tags) if tags else None,
            "metadata": json.dumps(metadata) if metadata else None,
        }

        parameters = {key: value for key, value in data.items() if value is not None}

        columns = ", ".join(f"[{key}]" for key in parameters.keys())
        values = ", ".join("?" for key in parameters.keys())
        updates = ", ".join(f"[{key}] = ?" for key in parameters.keys() if key != "id")

        # Use MERGE for upsert in SQL Server
        # nosec B608: table name 'threads' is hardcoded constant, parameters use ? placeholders
        query = f"""
            MERGE threads AS target
            USING (SELECT ? as id) AS source ON target.id = source.id
            WHEN MATCHED THEN
                UPDATE SET {updates}
            WHEN NOT MATCHED THEN
                INSERT ({columns})
                VALUES ({values});
        """

        # Prepare parameters for MERGE statement
        merge_params = (
            [thread_id] + list(parameters.values())[1:] + list(parameters.values())
        )

        self.execute_sql(sql=query, params=merge_params, expect_results=False)

        return ""

    async def update_memory(self) -> None:
        cursor = self.connection.cursor()

        # Create a temporary table for the latest records
        cursor.execute("""
            SELECT user_id, thread_id, message_id, positive_feedback, timestamp, role, content,
                   content_filter_results, tool_calls, tool_call_id, tool_call_function
            INTO #latest_chat_history
            FROM (
                SELECT user_id, thread_id, message_id, positive_feedback, timestamp, role, content,
                       content_filter_results, tool_calls, tool_call_id, tool_call_function,
                       ROW_NUMBER() OVER (PARTITION BY thread_id ORDER BY timestamp DESC) AS row_num
                FROM chat_history_summary
            ) AS LatestRecords
            WHERE row_num = 1
        """)

        # Clear the original table
        cursor.execute("DELETE FROM chat_history_summary")

        # Insert the latest records back into the original table
        cursor.execute("""
            INSERT INTO chat_history_summary (user_id, thread_id, message_id, positive_feedback, timestamp, role, content,
                                              content_filter_results, tool_calls, tool_call_id, tool_call_function)
            SELECT user_id, thread_id, message_id, positive_feedback, timestamp, role, content,
                   content_filter_results, tool_calls, tool_call_id, tool_call_function
            FROM #latest_chat_history
        """)

        # Drop the temporary table
        cursor.execute("DROP TABLE #latest_chat_history")
        cursor.close()
