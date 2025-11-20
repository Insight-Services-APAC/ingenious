"""SQLite database adapter for Ingenious chat history.

Provides lightweight local repository implementation for storing chat history,
threads, messages, and metadata using SQLite database.
"""

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional

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
from ingenious.db.connection_pool import ConnectionPool, SQLiteConnectionFactory
from ingenious.db.query_builder import QueryBuilder, SQLiteDialect
from ingenious.errors import (
    DatabaseQueryError,
)

logger = get_logger(__name__)


class sqlite_ChatHistoryRepository(BaseSQLRepository):
    """SQLite implementation of chat history repository.

    Provides lightweight local storage for chat history, threads, and messages
    using SQLite database with INSERT OR REPLACE operations.
    """

    def __init__(self, config: IngeniousSettings) -> None:
        """Initialize SQLite chat history repository with database path and connection pool.

        Args:
            config: Ingenious settings containing database path and configuration.
        """
        self.db_path = config.chat_history.database_path
        # Check if the directory exists, if not, create it
        db_dir_check = os.path.dirname(self.db_path)
        if not os.path.exists(db_dir_check):
            os.makedirs(db_dir_check)

        # Initialize connection pool
        pool_size = config.chat_history.connection_pool_size
        max_overflow = config.chat_history.connection_pool_max_overflow
        connection_factory = SQLiteConnectionFactory(self.db_path)
        self.pool = ConnectionPool(
            connection_factory, pool_size=pool_size, max_overflow=max_overflow
        )

        # Initialize query builder with SQLite dialect
        query_builder = QueryBuilder(SQLiteDialect())

        # Call parent constructor which will call _init_connection and _create_tables
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
        """Connection already initialized in __init__ via connection pool."""
        pass

    def _execute_sql(
        self, sql: str, params: list[Any] | None = None, expect_results: bool = True
    ) -> Any:
        if params is None:
            params = []
        try:
            with self.pool.get_connection() as connection:
                cursor = connection.cursor()
                logger.debug(
                    "Executing SQL query",
                    sql_preview=sql[:100] + "..." if len(sql) > 100 else sql,
                    param_count=len(params) if params else 0,
                    operation="sql_execute",
                )

                if expect_results:
                    res = cursor.execute(sql, params)
                    rows = res.fetchall()
                    result = [dict(row) for row in rows]
                    return result
                else:
                    connection.execute(sql, params)
                    connection.commit()

        except sqlite3.Error as e:
            logger.error(
                "SQLite error during query execution",
                error=str(e),
                sql_preview=sql[:100] + "..." if len(sql) > 100 else sql,
                param_count=len(params) if params else 0,
                operation="sql_execute",
            )
            raise DatabaseQueryError(
                "SQLite query execution failed",
                context={
                    "query_preview": sql[:100] + "..." if len(sql) > 100 else sql,
                    "param_count": len(params) if params else 0,
                    "expect_results": expect_results,
                },
                cause=e,
            ) from e

    def execute_sql(
        self, sql: str, params: list[Any] | None = None, expect_results: bool = True
    ) -> Any:
        """Legacy method for backward compatibility."""
        return self._execute_sql(sql, params, expect_results)

    def _create_table(self) -> None:
        """Legacy method for backward compatibility. Tables are now created via base class."""
        pass

    async def _get_user_by_id(self, user_id: str) -> IChatHistoryRepository.User | None:
        with self.pool.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """SELECT id, identifier, metadata, createdAt FROM users WHERE id = ?""",
                (user_id,),
            )
            row = cursor.fetchone()
            if row:
                return IChatHistoryRepository.User(
                    id=row[0], identifier=row[1], metadata=row[2], createdAt=row[3]
                )
            return None

    async def get_threads_for_user(
        self, identifier: str, thread_id: Optional[str]
    ) -> Optional[List[IChatHistoryRepository.ThreadDict]]:
        """Fetch all user threads up to self.user_thread_limit, or one thread by id if thread_id is provided."""
        if thread_id is None:
            user_threads_query = """
                SELECT
                    "id" AS thread_id,
                    "createdAt" AS thread_createdat,
                    "name" AS thread_name,
                    "userId" AS user_id,
                    "userIdentifier" AS user_identifier,
                    "tags" AS thread_tags,
                    "metadata" AS thread_metadata
                FROM threads
                WHERE "userIdentifier" = ?
                ORDER BY "createdAt" DESC
                LIMIT ?
            """

            user_threads = self.execute_sql(user_threads_query, [identifier, 100])
        else:
            user_threads_query = """
                SELECT
                    "id" AS thread_id,
                    "createdAt" AS thread_createdat,
                    "name" AS thread_name,
                    "userId" AS user_id,
                    "userIdentifier" AS user_identifier,
                    "tags" AS thread_tags,
                    "metadata" AS thread_metadata
                FROM threads
                WHERE "userIdentifier" = ? AND "id" = ?
                ORDER BY "createdAt" DESC
                LIMIT ?
            """

            user_threads = self.execute_sql(user_threads_query, [identifier, thread_id, 100])

        if not isinstance(user_threads, list):
            return None
        if not user_threads:
            return []
        else:
            thread_ids_list = []
            for thread in user_threads:
                thread_ids_list.append(str(thread["thread_id"]))

            # Create parameterized placeholders for IN clause
            thread_ids_placeholders = ",".join("?" * len(thread_ids_list))

        steps_feedbacks_query = f"""  # nosec B608: table name 'steps' is hardcoded constant, parameters use ? placeholders
            SELECT
                s."id" AS step_id,
                s."name" AS step_name,
                s."type" AS step_type,
                s."threadId" AS step_threadid,
                s."parentId" AS step_parentid,
                s."streaming" AS step_streaming,
                s."waitForAnswer" AS step_waitforanswer,
                s."isError" AS step_iserror,
                s."metadata" AS step_metadata,
                s."tags" AS step_tags,
                s."input" AS step_input,
                s."output" AS step_output,
                s."createdAt" AS step_createdat,
                s."start" AS step_start,
                s."end" AS step_end,
                s."generation" AS step_generation,
                s."showInput" AS step_showinput,
                s."language" AS step_language,
                s."indent" AS step_indent,
                f."value" AS feedback_value,
                f."comment" AS feedback_comment,
                f."id" AS feedback_id
            FROM steps s LEFT JOIN feedbacks f ON s."id" = f."forId"
            WHERE s."threadId" IN ({thread_ids_placeholders})
            ORDER BY s."createdAt" ASC
        """
        steps_feedbacks = self.execute_sql(steps_feedbacks_query, thread_ids_list)

        elements_query = f"""  # nosec B608: table name 'elements' is hardcoded constant, parameters use ? placeholders
            SELECT
                e."id" AS element_id,
                e."threadId" as element_threadid,
                e."type" AS element_type,
                e."chainlitKey" AS element_chainlitkey,
                e."url" AS element_url,
                e."objectKey" as element_objectkey,
                e."name" AS element_name,
                e."display" AS element_display,
                e."size" AS element_size,
                e."language" AS element_language,
                e."page" AS element_page,
                e."forId" AS element_forid,
                e."mime" AS element_mime
            FROM elements e
            WHERE e."threadId" IN ({thread_ids_placeholders})
        """
        elements = self.execute_sql(elements_query, thread_ids_list)

        thread_dicts = {}
        for thread in user_threads:
            thread_id = thread["thread_id"]
            if thread_id is not None:
                thread_dicts[thread_id] = IChatHistoryRepository.ThreadDict(
                    id=thread_id,
                    createdAt=thread["thread_createdat"],
                    name=thread["thread_name"],
                    userId=thread["user_id"],
                    userIdentifier=thread["user_identifier"],
                    tags=thread["thread_tags"],
                    metadata=thread[
                        "thread_id"
                    ],  # TODO: this gives NONE json.loads(thread["thread_metadata"]),
                    steps=[],
                    elements=[],
                )
        # Process steps_feedbacks to populate the steps in the corresponding ThreadDict
        if isinstance(steps_feedbacks, list):
            for step_feedback in steps_feedbacks:
                thread_id = step_feedback["step_threadid"]
                if thread_id is not None:
                    feedback = None
                    if step_feedback["feedback_value"] is not None:
                        feedback = IChatHistoryRepository.FeedbackDict(
                            forId=step_feedback["step_id"],
                            id=step_feedback.get("feedback_id"),
                            value=step_feedback["feedback_value"],
                            comment=step_feedback.get("feedback_comment"),
                        )
                    step_dict = IChatHistoryRepository.StepDict(
                        id=step_feedback["step_id"],
                        name=step_feedback["step_name"],
                        type=step_feedback["step_type"],
                        threadId=thread_id,
                        parentId=step_feedback.get("step_parentid"),
                        streaming=step_feedback.get("step_streaming", False),
                        waitForAnswer=step_feedback.get("step_waitforanswer"),
                        isError=step_feedback.get("step_iserror"),
                        metadata=(
                            step_feedback["step_metadata"]
                            if step_feedback.get("step_metadata") is not None
                            else {}
                        ),
                        tags=step_feedback.get("step_tags"),
                        input=(
                            step_feedback.get("step_input", "")
                            if step_feedback.get("step_showinput") not in [None, "false"]
                            else ""
                        ),
                        output=step_feedback.get("step_output", ""),
                        createdAt=step_feedback.get("step_createdat"),
                        start=step_feedback.get("step_start"),
                        end=step_feedback.get("step_end"),
                        generation=step_feedback.get("step_generation"),
                        showInput=step_feedback.get("step_showinput"),
                        language=step_feedback.get("step_language"),
                        indent=step_feedback.get("step_indent"),
                        feedback=feedback,
                    )
                    # Append the step to the steps list of the corresponding ThreadDict
                    thread_dicts[thread_id]["steps"].append(step_dict)

        if isinstance(elements, list):
            for element in elements:
                thread_id = element["element_threadid"]
                if thread_id is not None:
                    element_dict = IChatHistoryRepository.ElementDict(
                        id=element["element_id"],
                        threadId=thread_id,
                        type=element["element_type"],
                        chainlitKey=element.get("element_chainlitkey"),
                        url=element.get("element_url"),
                        objectKey=element.get("element_objectkey"),
                        name=element["element_name"],
                        display=element["element_display"],
                        size=element.get("element_size"),
                        language=element.get("element_language"),
                        autoPlay=element.get("element_autoPlay"),
                        playerConfig=element.get("element_playerconfig"),
                        page=element.get("element_page"),
                        forId=element.get("element_forid"),
                        mime=element.get("element_mime"),
                    )
                    thread_dicts[thread_id]["elements"].append(element_dict)  # type: ignore
        logger.debug(
            "Retrieved thread dictionaries",
            thread_count=len(thread_dicts),
            operation="get_threads_for_user",
        )
        return list(thread_dicts.values())

    async def add_step(
        self, step_dict: IChatHistoryRepository.StepDict
    ) -> IChatHistoryRepository.Step:
        """Add a step to the SQLite database.

        Args:
            step_dict: Step dictionary containing step data and metadata.

        Returns:
            Step object with generated ID and metadata.
        """
        logger.info(
            "Creating step in SQLite database",
            step_id=step_dict.get("id"),
            step_type=step_dict.get("type"),
            thread_id=step_dict.get("threadId"),
            operation="create_step",
        )

        # If disableFeedback is not provided, default to False
        step_dict["disableFeedback"] = step_dict.get("disableFeedback", False)

        step_dict["showInput"] = (
            str(step_dict.get("showInput", "")).lower() if "showInput" in step_dict else None
        )
        parameters = {
            key: value
            for key, value in step_dict.items()
            if value is not None and not (isinstance(value, dict) and not value)
        }
        parameters["metadata"] = json.dumps(step_dict.get("metadata", {}))
        parameters["generation"] = json.dumps(step_dict.get("generation", {}))
        columns = ", ".join(f'"{key}"' for key in parameters.keys())
        values = ", ".join("?" for key in parameters.keys())
        query = f"""  # nosec B608: table name 'steps' is hardcoded constant, parameters use ? placeholders
            INSERT INTO steps ({columns})
            VALUES ({values});
        """
        self.execute_sql(sql=query, params=list(parameters.values()), expect_results=False)

        # Return the created step
        from uuid import UUID

        return IChatHistoryRepository.Step(
            id=UUID(step_dict.get("id", "00000000-0000-0000-0000-000000000000")),
            name=step_dict.get("name", ""),
            type=step_dict.get("type", ""),
            threadId=UUID(step_dict.get("threadId", "00000000-0000-0000-0000-000000000000")),
            parentId=UUID(step_dict.get("parentId")) if step_dict.get("parentId") else None,
            disableFeedback=step_dict.get("disableFeedback", False),
            streaming=step_dict.get("streaming", False),
            waitForAnswer=step_dict.get("waitForAnswer"),
            isError=step_dict.get("isError"),
            metadata=step_dict.get("metadata"),
            tags=step_dict.get("tags"),
            input=step_dict.get("input"),
            output=step_dict.get("output"),
            createdAt=step_dict.get("createdAt"),
            start=step_dict.get("start"),
            end=step_dict.get("end"),
            generation=step_dict.get("generation"),
            showInput=str(step_dict.get("showInput"))
            if step_dict.get("showInput") is not None
            else None,
            language=step_dict.get("language"),
            indent=step_dict.get("indent"),
        )

    async def update_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, object]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Update or insert a thread using INSERT OR REPLACE.

        Args:
            thread_id: Unique identifier for the thread.
            name: Optional name for the thread.
            user_id: Optional user identifier owning the thread.
            metadata: Optional metadata dictionary for the thread.
            tags: Optional list of tags for the thread.

        Returns:
            Empty string on success.
        """
        logger.info(
            "Updating thread in SQLite",
            thread_id=thread_id,
            user_id=user_id,
            has_name=name is not None,
            has_metadata=metadata is not None,
            operation="update_thread",
        )
        user_identifier = None
        if user_id:
            logger.debug(
                "Retrieving user identifier for thread update",
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
            "tags": tags,
            "metadata": json.dumps(metadata) if metadata else None,
        }
        parameters = {
            key: value for key, value in data.items() if value is not None
        }  # Remove keys with None values
        columns = ", ".join(f'"{key}"' for key in parameters.keys())
        values = ", ".join("?" for key in parameters.keys())
        updates = ", ".join(
            f'"{key}" = EXCLUDED."{key}"' for key in parameters.keys() if key != "id"
        )
        query = f"""  # nosec B608: table name 'threads' is hardcoded constant, parameters use ? placeholders
            INSERT INTO threads ({columns})
            VALUES ({values})
            ON CONFLICT ("id") DO UPDATE
            SET {updates};
        """
        self.execute_sql(sql=query, params=list(parameters.values()), expect_results=False)

        return ""

    async def update_memory(self) -> None:
        """Update chat history summary to keep only the latest record per thread.

        Creates a temporary table with the latest record per thread, clears the
        summary table, and re-inserts only the latest records.
        """
        with self.pool.get_connection() as connection:
            cursor = connection.cursor()

            # Create a temporary table for the latest records
            cursor.execute("""
                CREATE TEMP TABLE latest_chat_history AS
                SELECT user_id, thread_id, message_id, positive_feedback, timestamp, role, content,
                       content_filter_results, tool_calls, tool_call_id, tool_call_function
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
                FROM latest_chat_history
            """)

            # Drop the temporary table
            cursor.execute("DROP TABLE latest_chat_history")

            cursor.close()
