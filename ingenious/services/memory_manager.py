"""Memory Manager for handling conversation context files through FileStorage abstraction.

This ensures that memory operations work with both local and Azure Blob Storage.
"""

import asyncio
import os
from typing import Any, Optional

from ingenious.config.settings import IngeniousSettings
from ingenious.core.structured_logging import get_logger
from ingenious.files.files_repository import FileStorage

logger = get_logger(__name__)


class MemoryManager:
    """Manages conversation memory/context files using the FileStorage abstraction.

    This allows memory operations to work with both local and Azure Blob Storage.
    """

    def __init__(self, config: IngeniousSettings, memory_path: Optional[str] = None):
        """Initialize MemoryManager with configuration.

        Args:
            config: Application configuration
            memory_path: Base path for memory files (defaults to config.chat_history.memory_path)
        """
        self.config = config
        self.memory_path = memory_path or config.chat_history.memory_path
        self.file_storage = FileStorage(config, category="data")

    def _get_memory_file_path(self, thread_id: Optional[str] = None) -> tuple[str, str]:
        """Get the file path and name for a memory file.

        Args:
            thread_id: Optional thread ID for thread-specific memory

        Returns:
            Tuple of (file_path, file_name)
        """
        if thread_id:
            file_path = f"memory/{thread_id}"
            file_name = "context.md"
        else:
            file_path = "memory"
            file_name = "context.md"

        return file_path, file_name

    async def read_memory(self, thread_id: Optional[str] = None, default_content: str = "") -> str:
        """Read memory content from storage.

        Args:
            thread_id: Optional thread ID for thread-specific memory
            default_content: Default content if memory file doesn't exist

        Returns:
            Memory content as string
        """
        try:
            file_path, file_name = self._get_memory_file_path(thread_id)

            # Check if file exists
            exists = await self.file_storage.check_if_file_exists(file_path, file_name)
            if not exists:
                return default_content

            # Read content
            content = await self.file_storage.read_file(file_name, file_path)
            return content if content else default_content

        except Exception as e:
            logger.error(
                "Failed to read memory from storage",
                error=str(e),
                thread_id=thread_id,
                file_path=file_path,
                file_name=file_name,
                operation="read_memory",
            )
            # Convert to structured error but don't raise to maintain backward compatibility
            # Return default content as fallback
            return default_content

    async def write_memory(self, content: str, thread_id: Optional[str] = None) -> bool:
        """Write memory content to storage.

        Args:
            content: Content to write
            thread_id: Optional thread ID for thread-specific memory

        Returns:
            True if successful, False otherwise
        """
        try:
            file_path, file_name = self._get_memory_file_path(thread_id)
            await self.file_storage.write_file(content, file_name, file_path)
            return True

        except Exception as e:
            logger.error(
                "Failed to write memory to storage",
                error=str(e),
                thread_id=thread_id,
                file_path=file_path,
                file_name=file_name,
                operation="write_memory",
            )
            # Return False to indicate failure
            return False

    async def maintain_memory(
        self, new_content: str, max_words: int = 150, thread_id: Optional[str] = None
    ) -> bool:
        """Maintain memory by appending new content and keeping only recent words.

        Args:
            new_content: New content to add
            max_words: Maximum number of words to keep
            thread_id: Optional thread ID for thread-specific memory

        Returns:
            True if successful, False otherwise
        """
        try:
            # Read current content
            current_content = await self.read_memory(thread_id)

            # Combine the current content and the new content
            combined_content = current_content + " " + new_content
            words = combined_content.split()

            # Keep only the last `max_words` words
            truncated_content = " ".join(words[-max_words:])

            # Write the truncated content back
            return await self.write_memory(truncated_content, thread_id)

        except Exception as e:
            logger.error(
                "Failed to maintain memory",
                error=str(e),
                thread_id=thread_id,
                max_words=max_words,
                new_content_length=len(new_content),
                operation="maintain_memory",
            )
            return False

    async def delete_memory(self, thread_id: Optional[str] = None) -> bool:
        """Delete memory content from storage.

        Args:
            thread_id: Optional thread ID for thread-specific memory

        Returns:
            True if successful, False otherwise
        """
        try:
            file_path, file_name = self._get_memory_file_path(thread_id)
            await self.file_storage.delete_file(file_name, file_path)
            return True

        except Exception as e:
            logger.error(
                "Failed to delete memory from storage",
                error=str(e),
                thread_id=thread_id,
                file_path=file_path,
                file_name=file_name,
                operation="delete_memory",
            )
            return False


class LegacyMemoryManager:
    """Legacy memory manager that provides backward compatibility for local file operations.

    This is used when the storage type is local or for fallback scenarios.
    """

    def __init__(self, memory_path: str):
        """Initialize LegacyMemoryManager with memory path.

        Args:
            memory_path: Base path for memory files
        """
        self.memory_path = memory_path

    def _get_memory_file_path(self, thread_id: Optional[str] = None) -> str:
        """Get the full file path for a memory file.

        Args:
            thread_id: Optional thread ID for thread-specific memory

        Returns:
            Full file path
        """
        if thread_id:
            return os.path.join(self.memory_path, thread_id, "context.md")
        else:
            return os.path.join(self.memory_path, "context.md")

    def read_memory(self, thread_id: Optional[str] = None, default_content: str = "") -> str:
        """Read memory content from local file.

        Args:
            thread_id: Optional thread ID for thread-specific memory
            default_content: Default content if memory file doesn't exist

        Returns:
            Memory content as string
        """
        try:
            file_path = self._get_memory_file_path(thread_id)

            if os.path.exists(file_path):
                with open(file_path, "r") as memory_file:
                    return memory_file.read()
            else:
                return default_content

        except Exception as e:
            logger.error(
                "Failed to read legacy memory file",
                error=str(e),
                thread_id=thread_id,
                file_path=file_path,
                operation="read_legacy_memory",
            )
            return default_content

    def write_memory(self, content: str, thread_id: Optional[str] = None) -> bool:
        """Write memory content to local file.

        Args:
            content: Content to write
            thread_id: Optional thread ID for thread-specific memory

        Returns:
            True if successful, False otherwise
        """
        try:
            file_path = self._get_memory_file_path(thread_id)

            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, "w") as memory_file:
                memory_file.write(content)
            return True

        except Exception as e:
            logger.error(
                "Failed to write legacy memory file",
                error=str(e),
                thread_id=thread_id,
                file_path=file_path,
                operation="write_legacy_memory",
            )
            return False

    def maintain_memory(
        self, new_content: str, max_words: int = 150, thread_id: Optional[str] = None
    ) -> bool:
        """Maintain memory by appending new content and keeping only recent words.

        Args:
            new_content: New content to add
            max_words: Maximum number of words to keep
            thread_id: Optional thread ID for thread-specific memory

        Returns:
            True if successful, False otherwise
        """
        try:
            file_path = self._get_memory_file_path(thread_id)

            # Read current content
            if os.path.exists(file_path):
                with open(file_path, "r") as memory_file:
                    current_content = memory_file.read()
            else:
                current_content = ""

            # Combine the current content and the new content
            combined_content = current_content + " " + new_content
            words = combined_content.split()

            # Keep only the last `max_words` words
            truncated_content = " ".join(words[-max_words:])

            # Write the truncated content back
            return self.write_memory(truncated_content, thread_id)

        except Exception as e:
            logger.error(
                "Failed to maintain legacy memory",
                error=str(e),
                thread_id=thread_id,
                max_words=max_words,
                new_content_length=len(new_content),
                operation="maintain_legacy_memory",
            )
            return False


def get_memory_manager(
    config: IngeniousSettings, memory_path: Optional[str] = None
) -> MemoryManager:
    """Get appropriate memory manager based on configuration.

    Args:
        config: Application configuration
        memory_path: Base path for memory files

    Returns:
        MemoryManager instance
    """
    return MemoryManager(config, memory_path)


def run_async_memory_operation(coro: Any) -> Any:
    """Helper function to run async memory operations in sync contexts.

    Args:
        coro: Coroutine to run

    Returns:
        Result of the coroutine
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're already in an async context, we need to handle this differently
            # For now, we'll use a simple approach and suggest refactoring to async
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError as e:
        # No event loop running, create a new one
        logger.debug(
            "No event loop running, creating new one",
            error=str(e),
            operation="async_memory_operation",
        )
        return asyncio.run(coro)
