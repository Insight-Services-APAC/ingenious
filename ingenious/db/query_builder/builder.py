"""Centralized query builder that generates database-specific SQL queries."""

from typing import Any

from .azuresql import AzureSQLDialect
from .base import Dialect


class QueryBuilder:
    """Centralized query builder that generates database-specific SQL queries.

    Uses a dialect pattern to generate SQL queries that are compatible with
    different database backends. Supports table creation, message operations,
    user and thread management, and memory operations.

    Attributes:
        dialect: Database dialect for generating database-specific SQL.
    """

    def __init__(self, dialect: Dialect) -> None:
        """Initialize the query builder with a database dialect.

        Args:
            dialect: Database dialect to use for SQL generation.
        """
        self.dialect = dialect
        self._data_types = dialect.get_data_types()

    def _get_data_type(self, generic_type: str) -> str:
        """Get database-specific data type for a generic type.

        Args:
            generic_type: Generic data type name (e.g., 'uuid', 'varchar').

        Returns:
            Database-specific data type string.
        """
        return self._data_types.get(generic_type, generic_type)

    def create_chat_history_table(self) -> str:
        """Generate CREATE TABLE query for chat_history table.

        Returns:
            Database-specific SQL to create the chat_history table with columns
            for user_id, thread_id, message_id, feedback, timestamps, roles, and tool calls.
        """
        table_name = "chat_history"
        prefix = self.dialect.get_create_table_if_not_exists_prefix()
        if "{table_name}" in prefix:
            prefix = prefix.format(table_name=table_name)

        # nosec B608: table name 'chat_history' is hardcoded constant, parameters use ? placeholders
        return f"""
            {prefix} {table_name} (
                user_id {self._get_data_type("varchar")},
                thread_id {self._get_data_type("varchar")},
                message_id {self._get_data_type("varchar")},
                positive_feedback {self._get_data_type("boolean")},
                timestamp {self._get_data_type("datetime")},
                role {self._get_data_type("varchar")},
                content {self._get_data_type("text")},
                content_filter_results {self._get_data_type("text")},
                tool_calls {self._get_data_type("text")},
                tool_call_id {self._get_data_type("varchar")},
                tool_call_function {self._get_data_type("varchar")}
            );
        """

    def create_chat_history_summary_table(self) -> str:
        """Generate CREATE TABLE query for chat_history_summary table.

        Returns:
            Database-specific SQL to create the chat_history_summary table with
            the same schema as chat_history for storing summarized memory.
        """
        table_name = "chat_history_summary"
        prefix = self.dialect.get_create_table_if_not_exists_prefix()
        if "{table_name}" in prefix:
            prefix = prefix.format(table_name=table_name)

        # nosec B608: table name 'chat_history_summary' is hardcoded constant, parameters use ? placeholders
        return f"""
            {prefix} {table_name} (
                user_id {self._get_data_type("varchar")},
                thread_id {self._get_data_type("varchar")},
                message_id {self._get_data_type("varchar")},
                positive_feedback {self._get_data_type("boolean")},
                timestamp {self._get_data_type("datetime")},
                role {self._get_data_type("varchar")},
                content {self._get_data_type("text")},
                content_filter_results {self._get_data_type("text")},
                tool_calls {self._get_data_type("text")},
                tool_call_id {self._get_data_type("varchar")},
                tool_call_function {self._get_data_type("varchar")}
            );
        """

    def create_users_table(self) -> str:
        """Generate CREATE TABLE query for users table.

        Returns:
            Database-specific SQL to create the users table with columns for
            id (UUID), identifier, metadata (JSON), and createdAt timestamp.
        """
        table_name = "users"
        prefix = self.dialect.get_create_table_if_not_exists_prefix()
        if "{table_name}" in prefix:
            prefix = prefix.format(table_name=table_name)

        # nosec B608: table name 'users' is hardcoded constant, parameters use ? placeholders
        return f"""
            {prefix} {table_name} (
                id {self._get_data_type("uuid")} PRIMARY KEY,
                identifier {self._get_data_type("varchar")} NOT NULL UNIQUE,
                metadata {self._get_data_type("json")} NOT NULL,
                createdAt {self._get_data_type("datetime")}
            );
        """

    def insert_message(self) -> str:
        """Generate INSERT query for adding a message to chat history.

        Returns:
            Parameterized INSERT query with 11 placeholders for message data.
        """
        return """
            INSERT INTO chat_history (
                user_id, thread_id, message_id, positive_feedback, timestamp,
                role, content, content_filter_results, tool_calls,
                tool_call_id, tool_call_function)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

    def insert_memory(self) -> str:
        """Generate INSERT query for adding a memory to chat history summary.

        Returns:
            Parameterized INSERT query with 11 placeholders for memory data.
        """
        return """
            INSERT INTO chat_history_summary (
                user_id, thread_id, message_id, positive_feedback, timestamp,
                role, content, content_filter_results, tool_calls,
                tool_call_id, tool_call_function)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

    def select_message(self) -> str:
        """Generate SELECT query for retrieving a specific message.

        Returns:
            Parameterized SELECT query with placeholders for message_id and thread_id.
        """
        return """
            SELECT user_id, thread_id, message_id, positive_feedback, timestamp, role, content,
                   content_filter_results, tool_calls, tool_call_id, tool_call_function
            FROM chat_history
            WHERE message_id = ? AND thread_id = ?
        """

    def select_latest_memory(self) -> str:
        """Generate SELECT query for retrieving the latest memory for a thread.

        Returns:
            Database-specific query to select the most recent memory by timestamp.
        """
        limit_clause = self.dialect.get_limit_clause(1)

        if isinstance(self.dialect, AzureSQLDialect):
            # nosec B608: table name 'chat_history_summary' is hardcoded constant, parameters use ? placeholders
            return f"""
                SELECT {limit_clause} user_id, thread_id, message_id, positive_feedback, timestamp, role, content,
                       content_filter_results, tool_calls, tool_call_id, tool_call_function
                FROM chat_history_summary
                WHERE thread_id = ?
                ORDER BY timestamp DESC
            """
        else:
            # nosec B608: table name 'chat_history_summary' is hardcoded constant, parameters use ? placeholders
            return f"""
                SELECT user_id, thread_id, message_id, positive_feedback, timestamp, role, content,
                       content_filter_results, tool_calls, tool_call_id, tool_call_function
                FROM chat_history_summary
                WHERE thread_id = ?
                ORDER BY timestamp DESC
                {limit_clause}
            """

    def update_message_feedback(self) -> str:
        """Generate UPDATE query for updating message feedback.

        Returns:
            Parameterized UPDATE query with placeholders for feedback, message_id, and thread_id.
        """
        return """
            UPDATE chat_history
            SET positive_feedback = ?
            WHERE message_id = ? AND thread_id = ?
        """

    def update_memory_feedback(self) -> str:
        """Generate UPDATE query for updating memory feedback.

        Returns:
            Parameterized UPDATE query with placeholders for feedback, message_id, and thread_id.
        """
        return """
            UPDATE chat_history_summary
            SET positive_feedback = ?
            WHERE message_id = ? AND thread_id = ?
        """

    def update_message_content_filter(self) -> str:
        """Generate UPDATE query for updating message content filter results.

        Returns:
            Parameterized UPDATE query with placeholders for filter results, message_id, and thread_id.
        """
        return """
            UPDATE chat_history
            SET content_filter_results = ?
            WHERE message_id = ? AND thread_id = ?
        """

    def update_memory_content_filter(self) -> str:
        """Generate UPDATE query for updating memory content filter results.

        Returns:
            Parameterized UPDATE query with placeholders for filter results, message_id, and thread_id.
        """
        return """
            UPDATE chat_history_summary
            SET content_filter_results = ?
            WHERE message_id = ? AND thread_id = ?
        """

    def insert_user(self) -> str:
        """Generate INSERT query for creating a new user.

        Returns:
            Parameterized INSERT query with placeholders for id, identifier, metadata, and createdAt.
        """
        return """
            INSERT INTO users (id, identifier, metadata, createdAt)
            VALUES (?, ?, ?, ?)
        """

    def select_user(self) -> str:
        """Generate SELECT query for retrieving a user by identifier.

        Returns:
            Parameterized SELECT query with placeholder for identifier.
        """
        return """
            SELECT id, identifier, metadata, createdAt
            FROM users
            WHERE identifier = ?
        """

    def select_thread_messages(self, limit: int = 5) -> str:
        """Generate SELECT query for retrieving recent thread messages.

        Args:
            limit: Maximum number of messages to retrieve. Defaults to 5.

        Returns:
            Database-specific query to select the most recent messages for a thread,
            ordered by timestamp ascending (oldest to newest).
        """
        if isinstance(self.dialect, AzureSQLDialect):
            # nosec B608: table name 'chat_history' is hardcoded constant, parameters use ? placeholders
            return f"""
                SELECT TOP {limit} user_id, thread_id, message_id, positive_feedback, timestamp, role, content,
                       content_filter_results, tool_calls, tool_call_id, tool_call_function
                FROM (
                    SELECT user_id, thread_id, message_id, positive_feedback, timestamp, role, content,
                           content_filter_results, tool_calls, tool_call_id, tool_call_function,
                           ROW_NUMBER() OVER (ORDER BY timestamp DESC) as rn
                    FROM chat_history
                    WHERE thread_id = ?
                ) AS ranked
                WHERE rn <= {limit}
                ORDER BY timestamp ASC
            """
        else:
            # nosec B608: table name 'chat_history' is hardcoded constant, parameters use ? placeholders
            return f"""
                SELECT *
                FROM (
                    SELECT user_id, thread_id, message_id, positive_feedback, timestamp, role, content,
                           content_filter_results, tool_calls, tool_call_id, tool_call_function
                    FROM chat_history
                    WHERE thread_id = ?
                    ORDER BY timestamp DESC
                    LIMIT {limit}
                ) AS last_five
                ORDER BY timestamp ASC
            """

    def select_thread_memory(self) -> str:
        """Generate SELECT query for retrieving thread memory.

        Returns:
            Database-specific query to select the most recent memory entry for a thread.
        """
        limit_clause = self.dialect.get_limit_clause(1)

        if isinstance(self.dialect, AzureSQLDialect):
            # nosec B608: table name 'chat_history_summary' is hardcoded constant, parameters use ? placeholders
            return f"""
                SELECT {limit_clause} user_id, thread_id, message_id, positive_feedback, timestamp, role, content,
                       content_filter_results, tool_calls, tool_call_id, tool_call_function
                FROM chat_history_summary
                WHERE thread_id = ?
                ORDER BY timestamp DESC
            """
        else:
            # nosec B608: table name 'chat_history_summary' is hardcoded constant, parameters use ? placeholders
            return f"""
                SELECT user_id, thread_id, message_id, positive_feedback, timestamp, role, content,
                       content_filter_results, tool_calls, tool_call_id, tool_call_function
                FROM chat_history_summary
                WHERE thread_id = ?
                ORDER BY timestamp DESC
                {limit_clause}
            """

    def select_thread_memory_context(self, limit: int = 10, content_length: int = 200) -> str:
        """Generate SELECT query for retrieving thread memory context with truncated content.

        This optimized query fetches only the last N messages with content truncated to
        the specified length, reducing data transfer and moving truncation to the database.

        Args:
            limit: Maximum number of recent messages to retrieve. Defaults to 10.
            content_length: Maximum content length to return per message. Defaults to 200.

        Returns:
            Database-specific query to select recent messages with truncated content,
            ordered by timestamp ascending (oldest to newest).
        """
        if isinstance(self.dialect, AzureSQLDialect):
            # nosec B608: table name 'chat_history' is hardcoded constant, parameters use ? placeholders
            return f"""
                SELECT TOP {limit} role, SUBSTRING(content, 1, {content_length}) as content
                FROM (
                    SELECT role, content,
                           ROW_NUMBER() OVER (ORDER BY timestamp DESC) as rn
                    FROM chat_history
                    WHERE thread_id = ?
                ) AS ranked
                WHERE rn <= {limit}
                ORDER BY rn DESC
            """
        else:
            # nosec B608: table name 'chat_history' is hardcoded constant, parameters use ? placeholders
            return f"""
                SELECT role, SUBSTR(content, 1, {content_length}) as content
                FROM (
                    SELECT role, content
                    FROM chat_history
                    WHERE thread_id = ?
                    ORDER BY timestamp DESC
                    LIMIT {limit}
                ) AS last_messages
                ORDER BY rowid DESC
            """

    def delete_thread(self) -> str:
        """Generate DELETE query for removing all messages in a thread.

        Returns:
            Parameterized DELETE query with placeholder for thread_id.
        """
        return """
            DELETE FROM chat_history
            WHERE thread_id = ?
        """

    def delete_thread_memory(self) -> str:
        """Generate DELETE query for removing thread memory.

        Returns:
            Parameterized DELETE query with placeholder for thread_id.
        """
        return """
            DELETE FROM chat_history_summary
            WHERE thread_id = ?
        """

    def delete_user_memory(self) -> str:
        """Generate DELETE query for removing all memory for a user.

        Returns:
            Parameterized DELETE query with placeholder for user_id.
        """
        return """
            DELETE FROM chat_history_summary
            WHERE user_id = ?
        """

    def get_query(self, query_type: str, **kwargs: Any) -> str:
        """Get a query by type name with optional parameters.

        Dynamically invokes a query method by name, allowing runtime
        query selection with optional parameters.

        Args:
            query_type: Name of the query method to invoke (e.g., 'insert_message').
            **kwargs: Optional parameters to pass to the query method.

        Returns:
            The SQL query string from the matching method, or empty string if not found.
        """
        method_name = query_type
        if hasattr(self, method_name):
            method = getattr(self, method_name)
            if callable(method):
                result = method(**kwargs)
                return str(result) if result is not None else ""
        return ""
