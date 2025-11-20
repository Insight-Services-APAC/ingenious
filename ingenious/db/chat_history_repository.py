"""Chat history repository interface and adapters.

Defines the abstract interface for chat history storage and provides adapters
for various backends (SQLite, Azure SQL, Cosmos DB). Includes data models for
users, threads, messages, steps, and elements.
"""

import importlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import (
    Dict,
    List,
    Literal,
    Optional,
    TypedDict,
    Union,
    cast,
)
from uuid import UUID

from ingenious.config import IngeniousSettings
from ingenious.core.structured_logging import get_logger
from ingenious.models.database_client import DatabaseClientType
from ingenious.models.message import Message

logger = get_logger(__name__)


class IChatHistoryRepository(ABC):
    """Abstract interface for chat history storage operations.

    Defines the contract for storing and retrieving chat history including
    users, threads, messages, steps, elements, and feedback across various
    database backends (SQLite, Azure SQL, Cosmos DB).
    """

    TrueStepType = Literal["run", "tool", "llm", "embedding", "retrieval", "rerank", "undefined"]

    MessageStepType = Literal["user_message", "assistant_message", "system_message"]

    # Alias for compatibility
    StepType = Union[TrueStepType, MessageStepType]

    ElementType = Literal[
        "image",
        "text",
        "pdf",
        "tasklist",
        "audio",
        "video",
        "file",
        "plotly",
        "component",
    ]
    ElementDisplay = Literal["inline", "side", "page"]
    ElementSize = Literal["small", "medium", "large"]

    class ElementDict(TypedDict):
        """Typed dictionary for element data transfer."""

        id: str
        threadId: Optional[str]
        type: "IChatHistoryRepository.ElementType"
        chainlitKey: Optional[str]
        url: Optional[str]
        objectKey: Optional[str]
        name: str
        display: "IChatHistoryRepository.ElementDisplay"
        size: Optional["IChatHistoryRepository.ElementSize"]
        language: Optional[str]
        page: Optional[int]
        autoPlay: Optional[bool]
        playerConfig: Optional[dict[str, object]]
        forId: Optional[str]
        mime: Optional[str]

    @dataclass
    class ChatHistory:
        """Dataclass representing a complete chat history record."""

        user_id: str
        thread_id: str
        message_id: str
        positive_feedback: Optional[bool]
        timestamp: str
        role: str
        content: str
        content_filter_results: Optional[str]
        tool_calls: Optional[str]
        tool_call_id: Optional[str]
        tool_call_function: Optional[str]

    @dataclass
    class User:
        """Dataclass representing a user entity."""

        id: UUID
        identifier: str
        metadata: dict[str, object]
        createdAt: Optional[str]

    @dataclass
    class Thread:
        """Dataclass representing a conversation thread."""

        id: UUID
        createdAt: Optional[str]
        name: Optional[str]
        userId: UUID
        userIdentifier: Optional[str]
        tags: Optional[List[str]]
        metadata: Optional[dict[str, object]]

    @dataclass
    class Step:
        """Dataclass representing a conversation step or turn."""

        id: UUID
        name: str
        type: str
        threadId: UUID
        parentId: Optional[UUID]
        disableFeedback: bool
        streaming: bool
        waitForAnswer: Optional[bool]
        isError: Optional[bool]
        metadata: Optional[dict[str, object]]
        tags: Optional[List[str]]
        input: Optional[str]
        output: Optional[str]
        createdAt: Optional[str]
        start: Optional[str]
        end: Optional[str]
        generation: Optional[dict[str, object]]
        showInput: Optional[str]
        language: Optional[str]
        indent: Optional[int]

    @dataclass
    class Element:
        """Dataclass representing a UI element or attachment."""

        id: UUID
        threadId: Optional[UUID]
        type: Optional[str]
        url: Optional[str]
        chainlitKey: Optional[str]
        name: str
        display: Optional[str]
        objectKey: Optional[str]
        size: Optional[str]
        page: Optional[int]
        language: Optional[str]
        forId: Optional[UUID]
        mime: Optional[str]

    @dataclass
    class Feedback:
        """Dataclass representing user feedback on a conversation step."""

        id: UUID
        forId: UUID
        threadId: UUID
        value: int
        comment: Optional[str]

    class FeedbackDict(TypedDict):
        """Typed dictionary for feedback data transfer."""

        forId: str
        id: Optional[str]
        value: Literal[0, 1]
        comment: Optional[str]

    class StepDict(TypedDict, total=False):
        """Typed dictionary for step data transfer with optional fields."""

        name: str
        type: "IChatHistoryRepository.StepType"
        id: str
        threadId: str
        parentId: Optional[str]
        disableFeedback: bool
        streaming: bool
        waitForAnswer: Optional[bool]
        isError: Optional[bool]
        metadata: Dict[str, object]
        tags: Optional[List[str]]
        input: str
        output: str
        createdAt: Optional[str]
        start: Optional[str]
        end: Optional[str]
        generation: Optional[Dict[str, object]]
        showInput: Optional[Union[bool, str]]
        language: Optional[str]
        indent: Optional[int]
        feedback: Optional["IChatHistoryRepository.FeedbackDict"]

    class ThreadDict(TypedDict):
        """Typed dictionary for thread data transfer with steps and elements."""

        id: str
        createdAt: str
        name: Optional[str]
        userId: Optional[str]
        userIdentifier: Optional[str]
        tags: Optional[List[str]]
        metadata: Optional[Dict[str, object]]
        steps: List["IChatHistoryRepository.StepDict"]
        elements: Optional[List["IChatHistoryRepository.ElementDict"]]

    def get_now(self) -> datetime:
        """Get the current UTC datetime.

        Returns:
            Current datetime object in UTC timezone.
        """
        return datetime.now(timezone.utc)

    def get_now_as_string(self) -> str:
        """Get the current UTC datetime as a formatted string.

        Returns:
            ISO-formatted datetime string with microseconds and timezone.
        """
        return self.get_now().strftime("%Y-%m-%d %H:%M:%S.%f%z")

    @abstractmethod
    async def update_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, object]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Update thread metadata and properties.

        Args:
            thread_id: Unique identifier for the thread.
            name: Optional display name for the thread.
            user_id: Optional user identifier associated with the thread.
            metadata: Optional key-value metadata dictionary.
            tags: Optional list of tags for categorization.

        Returns:
            The thread ID after successful update.
        """
        pass

    @abstractmethod
    async def add_message(self, message: Message) -> str:
        """Adds a message to the chat history."""
        pass

    @abstractmethod
    async def add_user(self, identifier: str) -> User:
        """Adds a user to the chat history database."""
        pass

    @abstractmethod
    async def get_user(self, identifier: str) -> User | None:
        """Gets a user from the chat history database."""
        pass

    @abstractmethod
    async def get_message(self, message_id: str, thread_id: str) -> Message | None:
        """Gets a message from the chat history."""
        pass

    @abstractmethod
    async def get_thread_messages(self, thread_id: str) -> list[Message]:
        """Retrieve all messages for a specific thread.

        Args:
            thread_id: Unique identifier for the thread.

        Returns:
            List of Message objects belonging to the thread.
        """
        pass

    @abstractmethod
    async def get_threads_for_user(
        self, identifier: str, thread_id: Optional[str]
    ) -> Optional[List["IChatHistoryRepository.ThreadDict"]]:
        """Retrieve all threads for a user, optionally filtered by thread ID.

        Args:
            identifier: User identifier to filter threads by.
            thread_id: Optional specific thread ID to retrieve.

        Returns:
            List of ThreadDict objects for the user, or None if no threads exist.
        """
        pass

    @abstractmethod
    async def update_message_feedback(
        self, message_id: str, thread_id: str, positive_feedback: bool | None
    ) -> None:
        """Update the feedback status for a specific message.

        Args:
            message_id: Unique identifier for the message.
            thread_id: Thread containing the message.
            positive_feedback: True for positive, False for negative, None to clear feedback.
        """
        pass

    @abstractmethod
    async def update_message_content_filter_results(
        self, message_id: str, thread_id: str, content_filter_results: dict[str, object]
    ) -> None:
        """Update content filter results for a specific message.

        Args:
            message_id: Unique identifier for the message.
            thread_id: Thread containing the message.
            content_filter_results: Dictionary containing content moderation results.
        """
        pass

    @abstractmethod
    async def delete_thread(self, thread_id: str) -> None:
        """Delete a thread and all associated messages.

        Args:
            thread_id: Unique identifier for the thread to delete.
        """
        pass


class ChatHistoryRepository:
    """Factory-based chat history repository with dynamic backend selection.

    Instantiates the appropriate repository implementation based on database
    type configuration (SQLite, Azure SQL, or Cosmos DB).
    """

    def __init__(self, db_type: DatabaseClientType, config: IngeniousSettings) -> None:
        """Initialize the chat history repository with dynamic database backend.

        Args:
            db_type: Type of database client to use (SQLite, AzureSQL, Cosmos, etc.).
            config: Application configuration settings.

        Raises:
            ValueError: If the specified database client type is not supported.
        """
        module_name = f"ingenious.db.{db_type.value.lower()}"
        class_name = f"{db_type.value.lower()}_ChatHistoryRepository"

        try:
            module = importlib.import_module(module_name)
            repository_class = getattr(module, class_name)
        except (ImportError, AttributeError) as e:
            raise ValueError(f"Unsupported database client type: {module_name}.{class_name}") from e

        self.repository = repository_class(config=config)

    async def update_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, object]] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Update thread metadata and properties through the repository adapter.

        Args:
            thread_id: Unique identifier for the thread.
            name: Optional display name for the thread.
            user_id: Optional user identifier associated with the thread.
            metadata: Optional key-value metadata dictionary.
            tags: Optional list of tags for categorization.

        Returns:
            The thread ID after successful update.
        """
        return str(
            await self.repository.update_thread(
                thread_id=thread_id,
                name=name,
                user_id=user_id,
                metadata=metadata,
            )
        )

    async def add_user(self, identifier: str) -> IChatHistoryRepository.User:
        """Add a new user to the chat history database.

        Args:
            identifier: Unique user identifier string.

        Returns:
            User object containing the created user information.
        """
        return cast(IChatHistoryRepository.User, await self.repository.add_user(identifier))

    async def add_step(self, step_dict: IChatHistoryRepository.StepDict) -> str:
        """Add a conversation step to the chat history.

        Args:
            step_dict: Dictionary containing step data including type, content, and metadata.

        Returns:
            Step ID as a string after successful creation.
        """
        return str(await self.repository.add_step(step_dict))

    async def get_user(self, identifier: str) -> IChatHistoryRepository.User | None:
        """Retrieve a user by their identifier.

        Args:
            identifier: Unique user identifier string.

        Returns:
            User object if found, None otherwise.
        """
        return cast(
            IChatHistoryRepository.User | None,
            await self.repository.get_user(identifier),
        )

    async def add_message(self, message: Message) -> str:
        """Add a message to the chat history.

        Args:
            message: Message object containing role, content, and metadata.

        Returns:
            Message ID as a string after successful creation.
        """
        return str(await self.repository.add_message(message))

    async def add_memory(self, memory: Message) -> str:
        """Add a memory entry to the chat history.

        Args:
            memory: Message object representing a memory to store.

        Returns:
            Memory ID as a string after successful creation.
        """
        return str(await self.repository.add_memory(memory))

    async def get_message(self, message_id: str, thread_id: str) -> Message | None:
        """Retrieve a specific message by ID and thread.

        Args:
            message_id: Unique identifier for the message.
            thread_id: Thread containing the message.

        Returns:
            Message object if found, None otherwise.
        """
        return cast(Message | None, await self.repository.get_message(message_id, thread_id))

    async def get_memory(self, message_id: str, thread_id: str) -> Message | None:
        """Retrieve a specific memory entry by ID and thread.

        Args:
            message_id: Unique identifier for the memory entry.
            thread_id: Thread containing the memory.

        Returns:
            Message object representing the memory if found, None otherwise.
        """
        return cast(Message | None, await self.repository.get_memory(message_id, thread_id))

    async def update_memory(self) -> None:
        """Update memory entries in the chat history.

        This method performs batch updates or maintenance on memory entries.
        """
        await self.repository.update_memory()
        return None

    async def get_thread_messages(self, thread_id: str) -> Optional[List[Message]]:
        """Retrieve all messages for a specific thread.

        Args:
            thread_id: Unique identifier for the thread.

        Returns:
            List of Message objects belonging to the thread, or None if thread not found.
        """
        return cast(
            Optional[List[Message]],
            await self.repository.get_thread_messages(thread_id),
        )

    async def get_thread_memory(self, thread_id: str) -> Optional[List[Message]]:
        """Retrieve all memory entries for a specific thread.

        Args:
            thread_id: Unique identifier for the thread.

        Returns:
            List of Message objects representing memories for the thread, or None if thread not found.
        """
        return cast(Optional[List[Message]], await self.repository.get_thread_memory(thread_id))

    async def get_thread_memory_context(
        self, thread_id: str, limit: int = 10, content_length: int = 200
    ) -> list[dict[str, str]]:
        """Retrieve optimized memory context for a thread with truncated content.

        This method fetches only the last N messages with content truncated at the
        database level, reducing data transfer and improving performance.

        Args:
            thread_id: Unique identifier for the thread.
            limit: Maximum number of recent messages to retrieve. Defaults to 10.
            content_length: Maximum content length per message. Defaults to 200.

        Returns:
            List of dicts with 'role' and 'content' keys, ordered oldest to newest.
        """
        return cast(
            list[dict[str, str]],
            await self.repository.get_thread_memory_context(thread_id, limit, content_length),
        )

    async def get_threads_for_user(
        self, identifier: str, thread_id: Optional[str]
    ) -> Optional[List[IChatHistoryRepository.ThreadDict]]:
        """Retrieve all threads for a user, optionally filtered by thread ID.

        Args:
            identifier: User identifier to filter threads by.
            thread_id: Optional specific thread ID to retrieve.

        Returns:
            List of ThreadDict objects for the user, or None if no threads exist.
        """
        return cast(
            Optional[List[IChatHistoryRepository.ThreadDict]],
            await self.repository.get_threads_for_user(identifier, thread_id),
        )

    async def update_message_feedback(
        self, message_id: str, thread_id: str, positive_feedback: bool | None
    ) -> None:
        """Update the feedback status for a specific message.

        Args:
            message_id: Unique identifier for the message.
            thread_id: Thread containing the message.
            positive_feedback: True for positive, False for negative, None to clear feedback.
        """
        await self.repository.update_message_feedback(message_id, thread_id, positive_feedback)
        return None

    async def update_memory_feedback(
        self, message_id: str, thread_id: str, positive_feedback: bool | None
    ) -> None:
        """Update the feedback status for a specific memory entry.

        Args:
            message_id: Unique identifier for the memory entry.
            thread_id: Thread containing the memory.
            positive_feedback: True for positive, False for negative, None to clear feedback.
        """
        await self.repository.update_memory_feedback(message_id, thread_id, positive_feedback)
        return None

    async def update_message_content_filter_results(
        self, message_id: str, thread_id: str, content_filter_results: dict[str, object]
    ) -> None:
        """Update content filter results for a specific message.

        Args:
            message_id: Unique identifier for the message.
            thread_id: Thread containing the message.
            content_filter_results: Dictionary containing content moderation results.
        """
        await self.repository.update_message_content_filter_results(
            message_id, thread_id, content_filter_results
        )
        return None

    async def update_memory_content_filter_results(
        self, message_id: str, thread_id: str, content_filter_results: dict[str, object]
    ) -> None:
        """Update content filter results for a specific memory entry.

        Args:
            message_id: Unique identifier for the memory entry.
            thread_id: Thread containing the memory.
            content_filter_results: Dictionary containing content moderation results.
        """
        await self.repository.update_memory_content_filter_results(
            message_id, thread_id, content_filter_results
        )
        return None

    async def delete_thread(self, thread_id: str) -> None:
        """Delete a thread and all associated messages.

        Args:
            thread_id: Unique identifier for the thread to delete.
        """
        await self.repository.delete_thread(thread_id)
        return None

    async def delete_thread_memory(self, thread_id: str) -> None:
        """Delete all memory entries for a specific thread.

        Args:
            thread_id: Unique identifier for the thread whose memory to delete.
        """
        await self.repository.delete_thread_memory(thread_id)
        return None

    async def delete_user_memory(self, user_id: str) -> None:
        """Delete all memory entries for a specific user.

        Args:
            user_id: Unique identifier for the user whose memory to delete.
        """
        await self.repository.delete_user_memory(user_id)
