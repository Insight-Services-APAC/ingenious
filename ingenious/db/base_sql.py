"""Base SQL repository implementation for chat history.

This module provides an abstract base class for SQL-based chat history repositories
that uses composition with QueryBuilder for database-agnostic query generation.
"""

import json
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from ingenious.config import IngeniousSettings
from ingenious.db.chat_history_repository import IChatHistoryRepository
from ingenious.db.query_builder import QueryBuilder
from ingenious.models.message import Message


class BaseSQLRepository(IChatHistoryRepository, ABC):
    """Abstract base class for SQL-based chat history repositories.

    Uses composition with QueryBuilder for database-agnostic query generation,
    while allowing database-specific connection handling and execution.
    """

    def __init__(self, config: IngeniousSettings, query_builder: QueryBuilder) -> None:
        """Initialize the SQL repository.

        Args:
            config: Application configuration settings.
            query_builder: Query builder for generating database-specific SQL.
        """
        self.config = config
        self.query_builder = query_builder
        self._init_connection()
        self._create_tables()

    @abstractmethod
    def _init_connection(self) -> None:
        """Initialize database connection.

        Subclasses implement database-specific connection initialization.
        """
        pass

    @abstractmethod
    def _execute_sql(
        self, sql: str, params: List[Any] | None = None, expect_results: bool = True
    ) -> Any:
        """Execute SQL with database-specific connection handling.

        Args:
            sql: SQL query to execute.
            params: Optional query parameters.
            expect_results: Whether to return query results. Defaults to True.

        Returns:
            Query results if expect_results is True, None otherwise.
        """
        pass

    def _create_tables(self) -> None:
        """Create all required database tables.

        Uses QueryBuilder to generate database-specific CREATE TABLE statements
        for chat_history, chat_history_summary, and users.
        """
        table_queries = [
            self.query_builder.create_chat_history_table(),
            self.query_builder.create_chat_history_summary_table(),
            self.query_builder.create_users_table(),
        ]

        for query in table_queries:
            self._execute_sql(query, expect_results=False)

    async def add_message(self, message: Message) -> str:
        """Add a message to the chat history.

        Args:
            message: Message object to add.

        Returns:
            The generated message_id.
        """
        message.message_id = str(uuid.uuid4())
        message.timestamp = datetime.now()

        query = self.query_builder.insert_message()
        params = [
            message.user_id,
            message.thread_id,
            message.message_id,
            message.positive_feedback,
            message.timestamp,
            message.role,
            message.content,
            message.content_filter_results,
            message.tool_calls,
            message.tool_call_id,
            message.tool_call_function,
        ]

        self._execute_sql(query, params, expect_results=False)
        return message.message_id

    async def add_memory(self, message: Message) -> str:
        """Add a memory message to the chat history summary.

        Args:
            message: Memory message object to add.

        Returns:
            The generated message_id.
        """
        message.message_id = str(uuid.uuid4())
        message.timestamp = datetime.now()

        query = self.query_builder.insert_memory()
        params = [
            message.user_id,
            message.thread_id,
            message.message_id,
            message.positive_feedback,
            message.timestamp,
            message.role,
            message.content,
            message.content_filter_results,
            message.tool_calls,
            message.tool_call_id,
            message.tool_call_function,
        ]

        self._execute_sql(query, params, expect_results=False)
        return message.message_id

    async def get_message(self, message_id: str, thread_id: str) -> Message | None:
        """Get a specific message by ID and thread ID.

        Args:
            message_id: Unique identifier for the message.
            thread_id: Thread identifier containing the message.

        Returns:
            Message object if found, None otherwise.
        """
        query = self.query_builder.select_message()
        params = [message_id, thread_id]

        result = self._execute_sql(query, params, expect_results=True)
        if result:
            row = result[0] if isinstance(result, list) else result
            return self._row_to_message(row)
        return None

    async def get_memory(self, message_id: str, thread_id: str) -> Message | None:
        """Get the latest memory for a thread.

        Args:
            message_id: Message identifier (unused, kept for interface compatibility).
            thread_id: Thread identifier to retrieve memory for.

        Returns:
            Most recent memory message for the thread, or None if not found.
        """
        query = self.query_builder.select_latest_memory()
        params = [thread_id]

        result = self._execute_sql(query, params, expect_results=True)
        if result:
            row = result[0] if isinstance(result, list) else result
            return self._row_to_message(row)
        return None

    async def update_message_feedback(
        self, message_id: str, thread_id: str, positive_feedback: bool | None
    ) -> None:
        """Update feedback for a message.

        Args:
            message_id: Message identifier.
            thread_id: Thread identifier.
            positive_feedback: Feedback value (True for positive, False for negative, None for none).
        """
        query = self.query_builder.update_message_feedback()
        params = [positive_feedback, message_id, thread_id]
        self._execute_sql(query, params, expect_results=False)

    async def update_memory_feedback(
        self, message_id: str, thread_id: str, positive_feedback: bool | None
    ) -> None:
        """Update feedback for a memory.

        Args:
            message_id: Message identifier.
            thread_id: Thread identifier.
            positive_feedback: Feedback value (True for positive, False for negative, None for none).
        """
        query = self.query_builder.update_memory_feedback()
        params = [positive_feedback, message_id, thread_id]
        self._execute_sql(query, params, expect_results=False)

    async def update_message_content_filter_results(
        self, message_id: str, thread_id: str, content_filter_results: dict[str, object]
    ) -> None:
        """Update content filter results for a message.

        Args:
            message_id: Message identifier.
            thread_id: Thread identifier.
            content_filter_results: Content filter results dictionary.
        """
        query = self.query_builder.update_message_content_filter()
        params = [str(content_filter_results), message_id, thread_id]
        self._execute_sql(query, params, expect_results=False)

    async def update_memory_content_filter_results(
        self, message_id: str, thread_id: str, content_filter_results: dict[str, object]
    ) -> None:
        """Update content filter results for a memory.

        Args:
            message_id: Message identifier.
            thread_id: Thread identifier.
            content_filter_results: Content filter results dictionary.
        """
        query = self.query_builder.update_memory_content_filter()
        params = [str(content_filter_results), message_id, thread_id]
        self._execute_sql(query, params, expect_results=False)

    async def add_user(
        self, identifier: str, metadata: dict[str, object] | None = None
    ) -> IChatHistoryRepository.User:
        """Add a new user to the database.

        Args:
            identifier: Unique identifier for the user.
            metadata: Optional metadata dictionary. Defaults to empty dict.

        Returns:
            Newly created User object.
        """
        if metadata is None:
            metadata = {}
        now = self.get_now()
        new_id = str(uuid.uuid4())

        query = self.query_builder.insert_user()
        params = [new_id, identifier, json.dumps(metadata), now]
        self._execute_sql(query, params, expect_results=False)

        return IChatHistoryRepository.User(
            id=uuid.UUID(new_id),
            identifier=identifier,
            metadata=metadata,
            createdAt=self.get_now_as_string(),
        )

    async def get_user(self, identifier: str) -> IChatHistoryRepository.User | None:
        """Get user by identifier, creating if not found.

        Args:
            identifier: Unique identifier for the user.

        Returns:
            User object, either existing or newly created.
        """
        query = self.query_builder.select_user()
        params = [identifier]

        result = self._execute_sql(query, params, expect_results=True)
        if result:
            row = result[0] if isinstance(result, list) else result
            return self._row_to_user(row)
        else:
            return await self.add_user(identifier)

    async def get_thread_messages(
        self, thread_id: str, limit: Optional[int] = None
    ) -> list[Message]:
        """Get recent messages for a thread.

        Args:
            thread_id: Thread identifier.
            limit: Maximum number of recent messages to retrieve.
                   If None, uses default query builder limit (typically 5).
                   For optimal performance, specify the exact number needed.

        Returns:
            List of recent messages for the thread, ordered by timestamp (oldest to newest).
        """
        if limit is not None:
            query = self.query_builder.select_thread_messages(limit=limit)
        else:
            query = self.query_builder.select_thread_messages()
        params = [thread_id]

        result = self._execute_sql(query, params, expect_results=True)
        if result:
            return [self._row_to_message(row) for row in result]
        return []

    async def get_thread_memory(self, thread_id: str) -> list[Message]:
        """Get memory for a thread.

        Args:
            thread_id: Thread identifier.

        Returns:
            List containing the most recent memory message for the thread.
        """
        query = self.query_builder.select_thread_memory()
        params = [thread_id]

        result = self._execute_sql(query, params, expect_results=True)
        if result:
            return [self._row_to_message(row) for row in result]
        return []

    async def delete_thread(self, thread_id: str) -> None:
        """Delete all messages for a thread.

        Args:
            thread_id: Thread identifier.
        """
        query = self.query_builder.delete_thread()
        params = [thread_id]
        self._execute_sql(query, params, expect_results=False)

    async def delete_thread_memory(self, thread_id: str) -> None:
        """Delete memory for a thread.

        Args:
            thread_id: Thread identifier.
        """
        query = self.query_builder.delete_thread_memory()
        params = [thread_id]
        self._execute_sql(query, params, expect_results=False)

    async def delete_user_memory(self, user_id: str) -> None:
        """Delete all memory for a user.

        Args:
            user_id: User identifier.
        """
        query = self.query_builder.delete_user_memory()
        params = [user_id]
        self._execute_sql(query, params, expect_results=False)

    def _row_to_message(self, row: Any) -> Message:
        """Convert database row to Message object.

        Args:
            row: Database row as dict or tuple.

        Returns:
            Message object populated from row data.
        """
        if isinstance(row, dict):
            return Message(
                user_id=row.get("user_id"),
                thread_id=row.get("thread_id"),
                message_id=row.get("message_id"),
                positive_feedback=row.get("positive_feedback"),
                timestamp=row.get("timestamp"),
                role=row.get("role"),
                content=row.get("content"),
                content_filter_results=row.get("content_filter_results"),
                tool_calls=row.get("tool_calls"),
                tool_call_id=row.get("tool_call_id"),
                tool_call_function=row.get("tool_call_function"),
            )
        else:
            # Assume row is tuple/list with positional values
            return Message(
                user_id=row[0],
                thread_id=row[1],
                message_id=row[2],
                positive_feedback=row[3],
                timestamp=row[4],
                role=row[5],
                content=row[6],
                content_filter_results=row[7],
                tool_calls=row[8],
                tool_call_id=row[9],
                tool_call_function=row[10],
            )

    def _row_to_user(self, row: Any) -> IChatHistoryRepository.User:
        """Convert database row to User object.

        Args:
            row: Database row as dict or tuple.

        Returns:
            User object populated from row data.
        """
        if isinstance(row, dict):
            return IChatHistoryRepository.User(
                id=UUID(row.get("id", "")),
                identifier=str(row.get("identifier", "")),
                metadata=dict(row.get("metadata", {})),
                createdAt=row.get("createdAt"),
            )
        else:
            # Assume row is tuple/list with positional values
            return IChatHistoryRepository.User(
                id=UUID(row[0]) if row[0] else UUID("00000000-0000-0000-0000-000000000000"),
                identifier=str(row[1]) if row[1] else "",
                metadata=dict(row[2]) if row[2] else {},
                createdAt=row[3],
            )
