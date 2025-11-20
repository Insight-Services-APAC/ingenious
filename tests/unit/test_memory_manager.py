"""Tests for ingenious.services.memory_manager module."""

import os
from unittest.mock import AsyncMock, Mock, mock_open, patch

import pytest

from ingenious.services.memory_manager import (
    LegacyMemoryManager,
    MemoryManager,
    get_memory_manager,
    run_async_memory_operation,
)


class TestMemoryManager:
    """Test cases for MemoryManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_config = Mock()
        self.mock_config.chat_history.memory_path = "/test/memory"
        self.mock_file_storage = Mock()

    def test_init_with_default_memory_path(self):
        """Test MemoryManager initialization with default memory path."""
        with patch("ingenious.services.memory_manager.FileStorage") as mock_fs:
            mock_fs.return_value = self.mock_file_storage

            manager = MemoryManager(self.mock_config)

            assert manager.config is self.mock_config
            assert manager.memory_path == "/test/memory"
            mock_fs.assert_called_once_with(self.mock_config, category="data")

    def test_init_with_custom_memory_path(self):
        """Test MemoryManager initialization with custom memory path."""
        with patch("ingenious.services.memory_manager.FileStorage") as mock_fs:
            mock_fs.return_value = self.mock_file_storage

            custom_path = "/custom/memory"
            manager = MemoryManager(self.mock_config, custom_path)

            assert manager.memory_path == custom_path

    def test_get_memory_file_path_without_thread_id(self):
        """Test _get_memory_file_path without thread ID."""
        with patch("ingenious.services.memory_manager.FileStorage"):
            manager = MemoryManager(self.mock_config)

            file_path, file_name = manager._get_memory_file_path()

            assert file_path == "memory"
            assert file_name == "context.md"

    def test_get_memory_file_path_with_thread_id(self):
        """Test _get_memory_file_path with thread ID."""
        with patch("ingenious.services.memory_manager.FileStorage"):
            manager = MemoryManager(self.mock_config)

            file_path, file_name = manager._get_memory_file_path("thread_123")

            assert file_path == "memory/thread_123"
            assert file_name == "context.md"

    @pytest.mark.asyncio
    async def test_read_memory_file_exists(self):
        """Test read_memory when file exists."""
        with patch("ingenious.services.memory_manager.FileStorage") as mock_fs:
            mock_fs.return_value = self.mock_file_storage
            self.mock_file_storage.check_if_file_exists = AsyncMock(return_value=True)
            self.mock_file_storage.read_file = AsyncMock(return_value="existing content")

            manager = MemoryManager(self.mock_config)
            result = await manager.read_memory("thread_123")

            assert result == "existing content"
            self.mock_file_storage.check_if_file_exists.assert_called_once_with(
                "memory/thread_123", "context.md"
            )
            self.mock_file_storage.read_file.assert_called_once_with(
                "context.md", "memory/thread_123"
            )

    @pytest.mark.asyncio
    async def test_read_memory_file_not_exists(self):
        """Test read_memory when file doesn't exist."""
        with patch("ingenious.services.memory_manager.FileStorage") as mock_fs:
            mock_fs.return_value = self.mock_file_storage
            self.mock_file_storage.check_if_file_exists = AsyncMock(return_value=False)

            manager = MemoryManager(self.mock_config)
            result = await manager.read_memory("thread_123", "default content")

            assert result == "default content"
            self.mock_file_storage.check_if_file_exists.assert_called_once()
            self.mock_file_storage.read_file.assert_not_called()

    @pytest.mark.asyncio
    async def test_read_memory_empty_content(self):
        """Test read_memory when file exists but is empty."""
        with patch("ingenious.services.memory_manager.FileStorage") as mock_fs:
            mock_fs.return_value = self.mock_file_storage
            self.mock_file_storage.check_if_file_exists = AsyncMock(return_value=True)
            self.mock_file_storage.read_file = AsyncMock(return_value="")

            manager = MemoryManager(self.mock_config)
            result = await manager.read_memory("thread_123", "default content")

            assert result == "default content"

    @pytest.mark.asyncio
    async def test_read_memory_exception_handling(self):
        """Test read_memory exception handling."""
        with patch("ingenious.services.memory_manager.FileStorage") as mock_fs:
            mock_fs.return_value = self.mock_file_storage
            self.mock_file_storage.check_if_file_exists = AsyncMock(
                side_effect=Exception("Storage error")
            )

            manager = MemoryManager(self.mock_config)

            with patch("ingenious.services.memory_manager.logger") as mock_logger:
                result = await manager.read_memory("thread_123", "fallback")

                assert result == "fallback"
                mock_logger.error.assert_called_once()
                call_args = mock_logger.error.call_args[1]
                assert call_args["error"] == "Storage error"
                assert call_args["thread_id"] == "thread_123"
                assert call_args["operation"] == "read_memory"

    @pytest.mark.asyncio
    async def test_write_memory_success(self):
        """Test successful write_memory."""
        with patch("ingenious.services.memory_manager.FileStorage") as mock_fs:
            mock_fs.return_value = self.mock_file_storage
            self.mock_file_storage.write_file = AsyncMock()

            manager = MemoryManager(self.mock_config)
            result = await manager.write_memory("test content", "thread_123")

            assert result is True
            self.mock_file_storage.write_file.assert_called_once_with(
                "test content", "context.md", "memory/thread_123"
            )

    @pytest.mark.asyncio
    async def test_write_memory_exception_handling(self):
        """Test write_memory exception handling."""
        with patch("ingenious.services.memory_manager.FileStorage") as mock_fs:
            mock_fs.return_value = self.mock_file_storage
            self.mock_file_storage.write_file = AsyncMock(side_effect=Exception("Write error"))

            manager = MemoryManager(self.mock_config)

            with patch("ingenious.services.memory_manager.logger") as mock_logger:
                result = await manager.write_memory("test content", "thread_123")

                assert result is False
                mock_logger.error.assert_called_once()
                call_args = mock_logger.error.call_args[1]
                assert call_args["error"] == "Write error"
                assert call_args["operation"] == "write_memory"

    @pytest.mark.asyncio
    async def test_maintain_memory_success(self):
        """Test successful maintain_memory."""
        with patch("ingenious.services.memory_manager.FileStorage") as mock_fs:
            mock_fs.return_value = self.mock_file_storage

            manager = MemoryManager(self.mock_config)

            # Mock read_memory and write_memory
            with (
                patch.object(manager, "read_memory", return_value="existing content") as mock_read,
                patch.object(manager, "write_memory", return_value=True) as mock_write,
            ):
                result = await manager.maintain_memory(
                    "new content", max_words=3, thread_id="thread_123"
                )

                assert result is True
                mock_read.assert_called_once_with("thread_123")
                # Should keep only last 3 words: "existing content new"
                mock_write.assert_called_once_with("content new content", "thread_123")

    @pytest.mark.asyncio
    async def test_maintain_memory_truncation(self):
        """Test maintain_memory word truncation."""
        with patch("ingenious.services.memory_manager.FileStorage") as mock_fs:
            mock_fs.return_value = self.mock_file_storage

            manager = MemoryManager(self.mock_config)

            long_content = "word1 word2 word3 word4 word5"
            with (
                patch.object(manager, "read_memory", return_value=long_content),
                patch.object(manager, "write_memory", return_value=True) as mock_write,
            ):
                await manager.maintain_memory("new_word", max_words=3)

                # Should keep only last 3 words: "word4 word5 new_word"
                mock_write.assert_called_once_with("word4 word5 new_word", None)

    @pytest.mark.asyncio
    async def test_maintain_memory_exception_handling(self):
        """Test maintain_memory exception handling."""
        with patch("ingenious.services.memory_manager.FileStorage") as mock_fs:
            mock_fs.return_value = self.mock_file_storage

            manager = MemoryManager(self.mock_config)

            with (
                patch.object(manager, "read_memory", side_effect=Exception("Read error")),
                patch("ingenious.services.memory_manager.logger") as mock_logger,
            ):
                result = await manager.maintain_memory("new content")

                assert result is False
                mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_memory_success(self):
        """Test successful delete_memory."""
        with patch("ingenious.services.memory_manager.FileStorage") as mock_fs:
            mock_fs.return_value = self.mock_file_storage
            self.mock_file_storage.delete_file = AsyncMock()

            manager = MemoryManager(self.mock_config)
            result = await manager.delete_memory("thread_123")

            assert result is True
            self.mock_file_storage.delete_file.assert_called_once_with(
                "context.md", "memory/thread_123"
            )

    @pytest.mark.asyncio
    async def test_delete_memory_exception_handling(self):
        """Test delete_memory exception handling."""
        with patch("ingenious.services.memory_manager.FileStorage") as mock_fs:
            mock_fs.return_value = self.mock_file_storage
            self.mock_file_storage.delete_file = AsyncMock(side_effect=Exception("Delete error"))

            manager = MemoryManager(self.mock_config)

            with patch("ingenious.services.memory_manager.logger") as mock_logger:
                result = await manager.delete_memory("thread_123")

                assert result is False
                mock_logger.error.assert_called_once()


class TestLegacyMemoryManager:
    """Test cases for LegacyMemoryManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.memory_path = "/test/legacy/memory"

    def test_init(self):
        """Test LegacyMemoryManager initialization."""
        manager = LegacyMemoryManager(self.memory_path)
        assert manager.memory_path == self.memory_path

    def test_get_memory_file_path_without_thread_id(self):
        """Test _get_memory_file_path without thread ID."""
        manager = LegacyMemoryManager(self.memory_path)
        result = manager._get_memory_file_path()

        expected = os.path.join(self.memory_path, "context.md")
        assert result == expected

    def test_get_memory_file_path_with_thread_id(self):
        """Test _get_memory_file_path with thread ID."""
        manager = LegacyMemoryManager(self.memory_path)
        result = manager._get_memory_file_path("thread_123")

        expected = os.path.join(self.memory_path, "thread_123", "context.md")
        assert result == expected

    def test_read_memory_file_exists(self):
        """Test read_memory when file exists."""
        manager = LegacyMemoryManager(self.memory_path)

        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data="file content")),
        ):
            result = manager.read_memory("thread_123")
            assert result == "file content"

    def test_read_memory_file_not_exists(self):
        """Test read_memory when file doesn't exist."""
        manager = LegacyMemoryManager(self.memory_path)

        with patch("os.path.exists", return_value=False):
            result = manager.read_memory("thread_123", "default")
            assert result == "default"

    def test_read_memory_exception_handling(self):
        """Test read_memory exception handling."""
        manager = LegacyMemoryManager(self.memory_path)

        with (
            patch("os.path.exists", side_effect=Exception("OS error")),
            patch("ingenious.services.memory_manager.logger") as mock_logger,
        ):
            result = manager.read_memory("thread_123", "fallback")
            assert result == "fallback"
            mock_logger.error.assert_called_once()

    def test_write_memory_success(self):
        """Test successful write_memory."""
        manager = LegacyMemoryManager(self.memory_path)

        with (
            patch("os.makedirs") as mock_makedirs,
            patch("builtins.open", mock_open()) as mock_file,
        ):
            result = manager.write_memory("test content", "thread_123")

            assert result is True
            mock_makedirs.assert_called_once()
            mock_file.assert_called_once()

    def test_write_memory_exception_handling(self):
        """Test write_memory exception handling."""
        manager = LegacyMemoryManager(self.memory_path)

        with (
            patch("os.makedirs", side_effect=Exception("OS error")),
            patch("ingenious.services.memory_manager.logger") as mock_logger,
        ):
            result = manager.write_memory("test content", "thread_123")

            assert result is False
            mock_logger.error.assert_called_once()

    def test_maintain_memory_success(self):
        """Test successful maintain_memory."""
        manager = LegacyMemoryManager(self.memory_path)

        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data="existing content")),
            patch.object(manager, "write_memory", return_value=True) as mock_write,
        ):
            result = manager.maintain_memory("new content", max_words=3, thread_id="thread_123")

            assert result is True
            mock_write.assert_called_once_with("content new content", "thread_123")


class TestModuleFunctions:
    """Test cases for module-level functions."""

    def test_get_memory_manager(self):
        """Test get_memory_manager function."""
        mock_config = Mock()

        with patch("ingenious.services.memory_manager.MemoryManager") as mock_mm:
            mock_instance = Mock()
            mock_mm.return_value = mock_instance

            result = get_memory_manager(mock_config, "/custom/path")

            assert result is mock_instance
            mock_mm.assert_called_once_with(mock_config, "/custom/path")

    def test_run_async_memory_operation_no_loop(self):
        """Test run_async_memory_operation when no event loop is running."""

        async def test_coro():
            return "async result"

        with (
            patch("asyncio.get_event_loop", side_effect=RuntimeError("No loop")),
            patch("asyncio.run", return_value="async result") as mock_run,
        ):
            result = run_async_memory_operation(test_coro())

            assert result == "async result"
            mock_run.assert_called_once()

    def test_run_async_memory_operation_with_stopped_loop(self):
        """Test run_async_memory_operation with stopped event loop."""

        async def test_coro():
            return "async result"

        mock_loop = Mock()
        mock_loop.is_running.return_value = False
        mock_loop.run_until_complete.return_value = "async result"

        with patch("asyncio.get_event_loop", return_value=mock_loop):
            result = run_async_memory_operation(test_coro())

            assert result == "async result"
            mock_loop.run_until_complete.assert_called_once()

    def test_run_async_memory_operation_with_running_loop(self):
        """Test run_async_memory_operation with running event loop."""

        async def test_coro():
            return "async result"

        mock_loop = Mock()
        mock_loop.is_running.return_value = True

        with (
            patch("asyncio.get_event_loop", return_value=mock_loop),
            patch("concurrent.futures.ThreadPoolExecutor") as mock_executor_class,
        ):
            mock_executor = Mock()
            mock_future = Mock()
            mock_future.result.return_value = "async result"
            mock_executor.submit.return_value = mock_future
            mock_executor_class.return_value.__enter__.return_value = mock_executor

            result = run_async_memory_operation(test_coro())

            assert result == "async result"
            mock_executor.submit.assert_called_once()

    def test_module_docstring(self):
        """Test that the module has appropriate documentation."""
        import ingenious.services.memory_manager as mm_module

        docstring = mm_module.__doc__
        assert docstring is not None
        assert "Memory Manager" in docstring
        assert "FileStorage abstraction" in docstring
