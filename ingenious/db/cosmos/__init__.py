"""Cosmos DB repository implementation for chat history management."""

import uuid
from typing import Any, Dict, List, Optional

from azure.cosmos import ContainerProxy, CosmosClient, PartitionKey

from ingenious.client.azure import AzureClientFactory
from ingenious.common.enums import AuthenticationMethod
from ingenious.config.settings import IngeniousSettings
from ingenious.core.structured_logging import get_logger
from ingenious.db.chat_history_repository import IChatHistoryRepository
from ingenious.errors import DatabaseQueryError
from ingenious.models.message import Message

logger = get_logger(__name__)


class cosmos_ChatHistoryRepository(IChatHistoryRepository):
    """Cosmos DB implementation of IChatHistoryRepository for managing chat history."""

    def __init__(self, config: IngeniousSettings) -> None:
        """Initialize Cosmos DB chat history repository.

        Args:
            config: Application configuration settings
        """
        self.config = config

        if config.cosmos_service is None:
            raise ValueError("Cosmos service configuration is missing")

        try:
            self.client: CosmosClient = AzureClientFactory.create_cosmos_client(
                cosmos_config=config.cosmos_service
            )
            database_id = config.cosmos_service.database_name or "ingenious-db"
        except Exception as e:
            raise DatabaseQueryError("Failed to create CosmosClient", cause=e)

        self._create_database(database_id)
        self._create_containers()

    def _create_database(self, database_id: str) -> None:
        authentication_method = getattr(self.config.cosmos_service, "authentication_method", None)

        if authentication_method == AuthenticationMethod.TOKEN:
            self.database = self.client.create_database_if_not_exists(id=database_id)
        else:
            self.database = self.client.get_database_client(database_id)

    def _create_containers(self) -> None:
        authentication_method = getattr(self.config.cosmos_service, "authentication_method", None)

        # Initialize containers based on authentication method
        if authentication_method == AuthenticationMethod.TOKEN:
            self.chat_history: ContainerProxy = self.database.create_container_if_not_exists(
                id="chat_history", partition_key=PartitionKey(path="/thread_id")
            )
            self.chat_history_summary: ContainerProxy = (
                self.database.create_container_if_not_exists(
                    id="chat_history_summary",
                    partition_key=PartitionKey(path="/thread_id"),
                )
            )
            self.users: ContainerProxy = self.database.create_container_if_not_exists(
                id="users", partition_key=PartitionKey(path="/identifier")
            )
        else:
            self.chat_history = self.database.get_container_client("chat_history")
            self.chat_history_summary = self.database.get_container_client("chat_history_summary")
            self.users = self.database.get_container_client("users")

    # Utility mappers
    def _message_to_doc(self, m: Message) -> Dict[str, Any]:
        return {
            "id": m.message_id or str(uuid.uuid4()),
            "user_id": m.user_id,
            "thread_id": m.thread_id,
            "message_id": m.message_id,
            "positive_feedback": m.positive_feedback,
            "timestamp": (m.timestamp.isoformat() if m.timestamp else None),
            "role": m.role,
            "content": m.content,
            "content_filter_results": m.content_filter_results,
            "tool_calls": m.tool_calls,
            "tool_call_id": m.tool_call_id,
            "tool_call_function": m.tool_call_function,
        }

    def _doc_to_message(self, d: Dict[str, Any]) -> Message:
        from datetime import datetime

        ts_val = d.get("timestamp")
        ts = datetime.fromisoformat(ts_val) if isinstance(ts_val, str) else None
        return Message(
            user_id=d.get("user_id"),
            thread_id=d.get("thread_id", ""),
            message_id=d.get("message_id"),
            positive_feedback=d.get("positive_feedback"),
            timestamp=ts,
            role=d.get("role", ""),
            content=d.get("content"),
            content_filter_results=d.get("content_filter_results"),
            tool_calls=d.get("tool_calls"),
            tool_call_id=d.get("tool_call_id"),
            tool_call_function=d.get("tool_call_function"),
        )

    # IChatHistoryRepository implementations
    async def update_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, object]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Update thread metadata in the repository.

        Args:
            thread_id: Unique identifier for the thread
            name: Optional thread name
            user_id: Optional user identifier
            metadata: Optional metadata dictionary
            tags: Optional list of tags

        Returns:
            Empty string (thread metadata storage is not used by Ingenious)
        """
        # Thread metadata storage is not used by Ingenious
        return ""

    async def add_message(self, message: Message) -> str:
        """Add a message to the chat history in Cosmos DB.

        Args:
            message: Message object to store

        Returns:
            Message ID of the created message

        Raises:
            DatabaseQueryError: If the message cannot be added to Cosmos DB
        """
        try:
            if not message.message_id:
                message.message_id = str(uuid.uuid4())
            doc = self._message_to_doc(message)
            self.chat_history.create_item(doc)
            return message.message_id
        except Exception as e:
            raise DatabaseQueryError("Failed to add message to Cosmos", cause=e)

    async def add_user(self, identifier: str) -> IChatHistoryRepository.User:
        """Add a new user to the repository in Cosmos DB.

        Args:
            identifier: User identifier string

        Returns:
            User object with generated ID and metadata

        Raises:
            DatabaseQueryError: If the user cannot be added to Cosmos DB
        """
        try:
            user_doc = {
                "id": str(uuid.uuid4()),
                "identifier": identifier,
                "metadata": {},
                "createdAt": self.get_now_as_string(),
            }
            self.users.upsert_item(user_doc)
            from uuid import UUID as _UUID

            return IChatHistoryRepository.User(
                id=_UUID(user_doc["id"]),
                identifier=identifier,
                metadata={},
                createdAt=user_doc["createdAt"],
            )
        except Exception as e:
            raise DatabaseQueryError("Failed to add user in Cosmos", cause=e)

    async def get_user(self, identifier: str) -> IChatHistoryRepository.User | None:
        """Retrieve a user from the repository by identifier.

        Args:
            identifier: User identifier string

        Returns:
            User object if found, or newly created user if not found

        Raises:
            DatabaseQueryError: If the user cannot be retrieved from Cosmos DB
        """
        try:
            results = list(
                self.users.query_items(
                    query="SELECT * FROM c WHERE c.identifier = @identifier",
                    parameters=[{"name": "@identifier", "value": identifier}],
                    enable_cross_partition_query=True,
                )
            )
            if results:
                d = results[0]
                from uuid import UUID as _UUID

                return IChatHistoryRepository.User(
                    id=_UUID(str(d.get("id") or "00000000-0000-0000-0000-000000000000")),
                    identifier=str(d.get("identifier", "")),
                    metadata=dict(d.get("metadata", {})),
                    createdAt=str(d.get("createdAt")) if d.get("createdAt") else None,
                )
            # Auto-create if not exists
            return await self.add_user(identifier)
        except Exception as e:
            raise DatabaseQueryError("Failed to get user from Cosmos", cause=e)

    async def get_message(self, message_id: str, thread_id: str) -> Message | None:
        """Retrieve a specific message from the chat history.

        Args:
            message_id: Unique identifier of the message
            thread_id: Thread identifier the message belongs to

        Returns:
            Message object if found, None otherwise

        Raises:
            DatabaseQueryError: If the message cannot be retrieved from Cosmos DB
        """
        try:
            results = list(
                self.chat_history.query_items(
                    query="SELECT TOP 1 * FROM c WHERE c.message_id = @mid AND c.thread_id = @tid",
                    parameters=[
                        {"name": "@mid", "value": message_id},
                        {"name": "@tid", "value": thread_id},
                    ],
                    enable_cross_partition_query=True,
                )
            )
            if results:
                return self._doc_to_message(results[0])
            return None
        except Exception as e:
            raise DatabaseQueryError("Failed to get message from Cosmos", cause=e)

    async def get_thread_messages(
        self, thread_id: str, limit: Optional[int] = None
    ) -> List[Message]:
        """Retrieve recent messages from a thread in chronological order.

        Args:
            thread_id: Thread identifier to retrieve messages from
            limit: Maximum number of messages to retrieve. If None, defaults to 5.
                   For optimal performance, specify the exact number needed.

        Returns:
            List of Message objects in chronological order (up to limit most recent)

        Raises:
            DatabaseQueryError: If messages cannot be retrieved from Cosmos DB
        """
        try:
            # Default to 5 for backward compatibility
            message_limit = limit if limit is not None else 5

            # Get last N by timestamp desc then reverse to asc
            docs = list(
                self.chat_history.query_items(
                    query=(
                        f"SELECT TOP {message_limit} c.user_id, c.thread_id, c.message_id, c.positive_feedback, c.timestamp, "
                        "c.role, c.content, c.content_filter_results, c.tool_calls, c.tool_call_id, c.tool_call_function "
                        "FROM c WHERE c.thread_id = @tid ORDER BY c.timestamp DESC"
                    ),
                    parameters=[{"name": "@tid", "value": thread_id}],
                    enable_cross_partition_query=True,
                )
            )
            messages = [self._doc_to_message(d) for d in reversed(docs)]
            return messages
        except Exception as e:
            raise DatabaseQueryError("Failed to get thread messages from Cosmos", cause=e)

    async def get_threads_for_user(
        self, identifier: str, thread_id: Optional[str]
    ) -> Optional[List[IChatHistoryRepository.ThreadDict]]:
        """Retrieve thread metadata for a user.

        Args:
            identifier: User identifier
            thread_id: Optional specific thread ID filter

        Returns:
            Empty list (thread metadata storage is not used by Ingenious)
        """
        # Thread metadata storage with steps/elements/feedbacks is not used by Ingenious
        return []

    async def update_message_feedback(
        self, message_id: str, thread_id: str, positive_feedback: bool | None
    ) -> None:
        """Update the feedback status for a specific message.

        Args:
            message_id: Unique identifier of the message
            thread_id: Thread identifier the message belongs to
            positive_feedback: Feedback value (True for positive, False for negative, None to clear)

        Raises:
            DatabaseQueryError: If feedback cannot be updated in Cosmos DB
        """
        try:
            # Fetch doc, patch and replace
            items = list(
                self.chat_history.query_items(
                    query="SELECT * FROM c WHERE c.message_id = @mid AND c.thread_id = @tid",
                    parameters=[
                        {"name": "@mid", "value": message_id},
                        {"name": "@tid", "value": thread_id},
                    ],
                    enable_cross_partition_query=True,
                )
            )
            if not items:
                return None
            doc = items[0]
            doc["positive_feedback"] = positive_feedback
            self.chat_history.replace_item(item=doc, body=doc)
            return None
        except Exception as e:
            raise DatabaseQueryError("Failed to update message feedback in Cosmos", cause=e)

    async def update_message_content_filter_results(
        self, message_id: str, thread_id: str, content_filter_results: dict[str, object]
    ) -> None:
        """Update content filter results for a specific message.

        Args:
            message_id: Unique identifier of the message
            thread_id: Thread identifier the message belongs to
            content_filter_results: Dictionary containing content filter results

        Raises:
            DatabaseQueryError: If content filter results cannot be updated in Cosmos DB
        """
        try:
            items = list(
                self.chat_history.query_items(
                    query="SELECT * FROM c WHERE c.message_id = @mid AND c.thread_id = @tid",
                    parameters=[
                        {"name": "@mid", "value": message_id},
                        {"name": "@tid", "value": thread_id},
                    ],
                    enable_cross_partition_query=True,
                )
            )
            if not items:
                return None
            doc = items[0]
            doc["content_filter_results"] = content_filter_results
            self.chat_history.replace_item(item=doc, body=doc)
            return None
        except Exception as e:
            raise DatabaseQueryError("Failed to update message CFR in Cosmos", cause=e)

    async def update_memory_feedback(
        self, message_id: str, thread_id: str, positive_feedback: bool | None
    ) -> None:
        """Update the feedback status for a memory entry in chat history summary.

        Args:
            message_id: Unique identifier of the memory entry
            thread_id: Thread identifier the memory belongs to
            positive_feedback: Feedback value (True for positive, False for negative, None to clear)

        Raises:
            DatabaseQueryError: If memory feedback cannot be updated in Cosmos DB
        """
        try:
            items = list(
                self.chat_history_summary.query_items(
                    query="SELECT * FROM c WHERE c.message_id = @mid AND c.thread_id = @tid",
                    parameters=[
                        {"name": "@mid", "value": message_id},
                        {"name": "@tid", "value": thread_id},
                    ],
                    enable_cross_partition_query=True,
                )
            )
            if not items:
                return None
            doc = items[0]
            doc["positive_feedback"] = positive_feedback
            self.chat_history_summary.replace_item(item=doc, body=doc)
            return None
        except Exception as e:
            raise DatabaseQueryError("Failed to update memory feedback in Cosmos", cause=e)

    async def update_memory_content_filter_results(
        self, message_id: str, thread_id: str, content_filter_results: dict[str, object]
    ) -> None:
        """Update content filter results for a memory entry in chat history summary.

        Args:
            message_id: Unique identifier of the memory entry
            thread_id: Thread identifier the memory belongs to
            content_filter_results: Dictionary containing content filter results

        Raises:
            DatabaseQueryError: If memory content filter results cannot be updated in Cosmos DB
        """
        try:
            items = list(
                self.chat_history_summary.query_items(
                    query="SELECT * FROM c WHERE c.message_id = @mid AND c.thread_id = @tid",
                    parameters=[
                        {"name": "@mid", "value": message_id},
                        {"name": "@tid", "value": thread_id},
                    ],
                    enable_cross_partition_query=True,
                )
            )
            if not items:
                return None
            doc = items[0]
            doc["content_filter_results"] = content_filter_results
            self.chat_history_summary.replace_item(item=doc, body=doc)
            return None
        except Exception as e:
            raise DatabaseQueryError("Failed to update memory CFR in Cosmos", cause=e)

    async def add_memory(self, message: Message) -> str:
        """Add a memory entry to the chat history summary in Cosmos DB.

        Args:
            message: Message object to store as memory

        Returns:
            Message ID of the created memory entry

        Raises:
            DatabaseQueryError: If the memory cannot be added to Cosmos DB
        """
        try:
            if not message.message_id:
                message.message_id = str(uuid.uuid4())
            doc = self._message_to_doc(message)
            self.chat_history_summary.create_item(doc)
            return message.message_id
        except Exception as e:
            raise DatabaseQueryError("Failed to add memory to Cosmos", cause=e)

    async def get_memory(self, message_id: str, thread_id: str) -> Message | None:
        """Retrieve the most recent memory entry for a thread.

        Args:
            message_id: Message ID (not used in query, kept for interface compatibility)
            thread_id: Thread identifier to retrieve memory from

        Returns:
            Most recent Message object from memory, or None if not found

        Raises:
            DatabaseQueryError: If memory cannot be retrieved from Cosmos DB
        """
        try:
            docs = list(
                self.chat_history_summary.query_items(
                    query=(
                        "SELECT TOP 1 * FROM c WHERE c.thread_id = @tid ORDER BY c.timestamp DESC"
                    ),
                    parameters=[{"name": "@tid", "value": thread_id}],
                    enable_cross_partition_query=True,
                )
            )
            if docs:
                return self._doc_to_message(docs[0])
            return None
        except Exception as e:
            raise DatabaseQueryError("Failed to get memory from Cosmos", cause=e)

    async def update_memory(self) -> None:
        """Update memory aggregation.

        For Cosmos DB implementation, memory is stored directly and no aggregation is performed.
        This is a no-op method for interface compatibility.
        """
        # For Cosmos, memory is already stored; no-op or could implement aggregation
        return None

    async def get_thread_memory(self, thread_id: str) -> List[Message]:
        """Retrieve the most recent memory entry for a thread as a list.

        Args:
            thread_id: Thread identifier to retrieve memory from

        Returns:
            List containing the most recent Message object from memory (empty if not found)

        Raises:
            DatabaseQueryError: If thread memory cannot be retrieved from Cosmos DB
        """
        try:
            docs = list(
                self.chat_history_summary.query_items(
                    query=(
                        "SELECT TOP 1 * FROM c WHERE c.thread_id = @tid ORDER BY c.timestamp DESC"
                    ),
                    parameters=[{"name": "@tid", "value": thread_id}],
                    enable_cross_partition_query=True,
                )
            )
            return [self._doc_to_message(d) for d in docs]
        except Exception as e:
            raise DatabaseQueryError("Failed to get thread memory from Cosmos", cause=e)

    async def delete_thread(self, thread_id: str) -> None:
        """Delete all messages and memory entries for a thread.

        Args:
            thread_id: Thread identifier to delete

        Raises:
            DatabaseQueryError: If thread cannot be deleted from Cosmos DB
        """
        try:
            # Delete messages
            docs = list(
                self.chat_history.query_items(
                    query="SELECT c.id FROM c WHERE c.thread_id = @tid",
                    parameters=[{"name": "@tid", "value": thread_id}],
                    enable_cross_partition_query=True,
                )
            )
            for d in docs:
                self.chat_history.delete_item(item=d["id"], partition_key=thread_id)

            # Delete memory
            docs = list(
                self.chat_history_summary.query_items(
                    query="SELECT c.id FROM c WHERE c.thread_id = @tid",
                    parameters=[{"name": "@tid", "value": thread_id}],
                    enable_cross_partition_query=True,
                )
            )
            for d in docs:
                self.chat_history_summary.delete_item(item=d["id"], partition_key=thread_id)

            return None
        except Exception as e:
            raise DatabaseQueryError("Failed to delete thread in Cosmos", cause=e)

    async def delete_thread_memory(self, thread_id: str) -> None:
        """Delete all memory entries for a specific thread.

        Args:
            thread_id: Thread identifier to delete memory from

        Raises:
            DatabaseQueryError: If thread memory cannot be deleted from Cosmos DB
        """
        try:
            docs = list(
                self.chat_history_summary.query_items(
                    query="SELECT c.id FROM c WHERE c.thread_id = @tid",
                    parameters=[{"name": "@tid", "value": thread_id}],
                    enable_cross_partition_query=True,
                )
            )
            for d in docs:
                self.chat_history_summary.delete_item(item=d["id"], partition_key=thread_id)
            return None
        except Exception as e:
            raise DatabaseQueryError("Failed to delete thread memory in Cosmos", cause=e)

    async def delete_user_memory(self, user_id: str) -> None:
        """Delete all memory entries for a specific user across all threads.

        Args:
            user_id: User identifier to delete memory for

        Raises:
            DatabaseQueryError: If user memory cannot be deleted from Cosmos DB
        """
        try:
            docs = list(
                self.chat_history_summary.query_items(
                    query="SELECT c.id, c.thread_id FROM c WHERE c.user_id = @uid",
                    parameters=[{"name": "@uid", "value": user_id}],
                    enable_cross_partition_query=True,
                )
            )
            for d in docs:
                # For user memory, partition is thread-based
                thread_pk = d.get("thread_id")
                if thread_pk is None:
                    continue
                self.chat_history_summary.delete_item(item=d["id"], partition_key=thread_pk)
            return None
        except Exception as e:
            raise DatabaseQueryError("Failed to delete user memory in Cosmos", cause=e)

    async def add_step(self, step_dict: IChatHistoryRepository.StepDict) -> str:
        """Add a step to the repository.

        Args:
            step_dict: Dictionary containing step information

        Returns:
            Step ID from the provided dictionary (step storage is not used by Ingenious)
        """
        # Step storage is not used by Ingenious
        return str(step_dict.get("id", ""))

    async def get_thread(self, thread_id: str) -> List[IChatHistoryRepository.Thread]:
        """Retrieve thread metadata from the repository.

        Args:
            thread_id: Thread identifier to retrieve

        Returns:
            Empty list (thread metadata storage is not used by Ingenious)
        """
        # Thread metadata storage is not used by Ingenious
        return []
