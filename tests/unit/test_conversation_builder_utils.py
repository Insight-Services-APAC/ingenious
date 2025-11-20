"""Tests for ingenious.utils.conversation_builder module."""

from unittest.mock import AsyncMock, Mock, mock_open, patch

import pytest

from ingenious.utils.conversation_builder import (
    Sync_Prompt_Templates,
    build_assistant_message,
    build_message,
    build_system_prompt,
    build_user_message,
)


class TestBuildSystemPrompt:
    """Test cases for build_system_prompt function."""

    def test_build_system_prompt_without_user_name(self):
        """Test building system prompt without user name."""
        result = build_system_prompt("You are a helpful assistant")

        expected = {"role": "system", "content": "You are a helpful assistant"}
        assert result == expected

    def test_build_system_prompt_with_user_name(self):
        """Test building system prompt with user name."""
        result = build_system_prompt("You are a helpful assistant", user_name="alice")

        expected = {
            "role": "system",
            "content": "You are a helpful assistant",
            "name": "alice",
        }
        assert result == expected

    def test_build_system_prompt_with_empty_prompt(self):
        """Test building system prompt with empty prompt."""
        result = build_system_prompt("")

        expected = {"role": "system", "content": ""}
        assert result == expected

    def test_build_system_prompt_with_none_user_name(self):
        """Test building system prompt with None user name."""
        result = build_system_prompt("Test prompt", user_name=None)

        expected = {"role": "system", "content": "Test prompt"}
        assert result == expected
        assert "name" not in result


class TestBuildUserMessage:
    """Test cases for build_user_message function."""

    def test_build_user_message_without_user_name(self):
        """Test building user message without user name."""
        result = build_user_message("Hello, how are you?", user_name=None)

        expected = {"role": "user", "content": "Hello, how are you?"}
        assert result == expected
        assert "name" not in result

    def test_build_user_message_with_user_name(self):
        """Test building user message with user name."""
        result = build_user_message("Hello, how are you?", user_name="bob")

        expected = {"role": "user", "content": "Hello, how are you?", "name": "bob"}
        assert result == expected

    def test_build_user_message_with_empty_prompt(self):
        """Test building user message with empty prompt."""
        result = build_user_message("", user_name="charlie")

        expected = {"role": "user", "content": "", "name": "charlie"}
        assert result == expected


class TestBuildAssistantMessage:
    """Test cases for build_assistant_message function."""

    def test_build_assistant_message_with_content_only(self):
        """Test building assistant message with content only."""
        result = build_assistant_message("I'm doing well, thank you!")

        expected = {"role": "assistant", "content": "I'm doing well, thank you!"}
        assert result == expected

    def test_build_assistant_message_with_none_content(self):
        """Test building assistant message with None content."""
        result = build_assistant_message(content=None)

        expected = {"role": "assistant"}
        assert result == expected
        assert "content" not in result

    def test_build_assistant_message_with_tool_calls(self):
        """Test building assistant message with tool calls."""
        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"location":"NYC"}'},
            }
        ]
        result = build_assistant_message("Let me check the weather", tool_calls=tool_calls)

        expected = {
            "role": "assistant",
            "content": "Let me check the weather",
            "tool_calls": tool_calls,
        }
        assert result == expected

    def test_build_assistant_message_with_tool_calls_only(self):
        """Test building assistant message with tool calls and no content."""
        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"location":"NYC"}'},
            }
        ]
        result = build_assistant_message(content=None, tool_calls=tool_calls)

        expected = {"role": "assistant", "tool_calls": tool_calls}
        assert result == expected
        assert "content" not in result

    def test_build_assistant_message_with_empty_tool_calls(self):
        """Test building assistant message with empty tool calls list."""
        result = build_assistant_message("Hello", tool_calls=[])

        expected = {"role": "assistant", "content": "Hello"}
        assert result == expected
        assert "tool_calls" not in result


class TestBuildMessage:
    """Test cases for build_message function."""

    def test_build_message_system_role(self):
        """Test building message with system role."""
        result = build_message("system", "You are helpful", user_name="alice")

        expected = {"role": "system", "content": "You are helpful"}
        assert result == expected

    def test_build_message_user_role(self):
        """Test building message with user role."""
        result = build_message("user", "Hello there!", user_name="bob")

        expected = {"role": "user", "content": "Hello there!", "name": "bob"}
        assert result == expected

    def test_build_message_assistant_role(self):
        """Test building message with assistant role."""
        result = build_message("assistant", "Hi! How can I help?", user_name="charlie")

        expected = {"role": "assistant", "content": "Hi! How can I help?"}
        assert result == expected

    def test_build_message_invalid_role(self):
        """Test building message with invalid role raises ValueError."""
        with pytest.raises(ValueError, match="Invalid message role"):
            build_message("invalid_role", "Some content")

    def test_build_message_with_none_content(self):
        """Test building message with None content."""
        result = build_message("assistant", None)

        expected = {"role": "assistant"}
        assert result == expected


class TestSyncPromptTemplates:
    """Test cases for Sync_Prompt_Templates function."""

    @pytest.mark.asyncio
    @patch("ingenious.utils.conversation_builder.FileStorage")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.open", new_callable=mock_open)
    async def test_sync_prompt_templates_azure_storage(
        self, mock_file_open, mock_mkdir, mock_file_storage
    ):
        """Test syncing prompt templates from Azure storage."""
        # Mock config
        mock_config = Mock()
        mock_config.file_storage.revisions.storage_type = "azure"

        # Mock FileStorage instance
        mock_fs_instance = Mock()
        mock_fs_instance.list_files = AsyncMock(
            return_value=[
                "prompts/v1/template1.jinja",
                "prompts/v1/template2.jinja",
                "prompts/v1/not_jinja.txt",
            ]
        )
        mock_fs_instance.read_file = AsyncMock(
            side_effect=["Template 1 content", "Template 2 content"]
        )
        mock_file_storage.return_value = mock_fs_instance

        # Execute function
        await Sync_Prompt_Templates(mock_config, "v1")

        # Verify FileStorage was created correctly
        mock_file_storage.assert_called_once_with(mock_config, category="revisions")

        # Verify list_files was called
        mock_fs_instance.list_files.assert_called_once_with(file_path="prompts/v1")

        # Verify read_file was called for each .jinja file (2 times)
        assert mock_fs_instance.read_file.call_count == 2
        mock_fs_instance.read_file.assert_any_call(
            file_name="template1.jinja", file_path="prompts/v1"
        )
        mock_fs_instance.read_file.assert_any_call(
            file_name="template2.jinja", file_path="prompts/v1"
        )

        # Verify directory creation
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

        # Verify files were written (2 times)
        assert mock_file_open.call_count == 2

    @pytest.mark.asyncio
    @patch("ingenious.utils.conversation_builder.FileStorage")
    @patch("ingenious.utils.conversation_builder.logger")
    async def test_sync_prompt_templates_local_storage(self, mock_logger, mock_file_storage):
        """Test syncing prompt templates with local storage."""
        # Mock config
        mock_config = Mock()
        mock_config.file_storage.revisions.storage_type = "local"

        # Execute function
        await Sync_Prompt_Templates(mock_config, "v1")

        # Verify FileStorage was created
        mock_file_storage.assert_called_once_with(mock_config, category="revisions")

        # Verify debug log was called for local storage
        mock_logger.debug.assert_called_once_with(
            "Local storage type detected", storage_type="local"
        )

    @pytest.mark.asyncio
    @patch("ingenious.utils.conversation_builder.FileStorage")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.open", new_callable=mock_open)
    async def test_sync_prompt_templates_no_jinja_files(
        self, mock_file_open, mock_mkdir, mock_file_storage
    ):
        """Test syncing when no .jinja files are found."""
        # Mock config
        mock_config = Mock()
        mock_config.file_storage.revisions.storage_type = "azure"

        # Mock FileStorage instance with no .jinja files
        mock_fs_instance = Mock()
        mock_fs_instance.list_files = AsyncMock(
            return_value=["prompts/v1/not_jinja.txt", "prompts/v1/also_not_jinja.md"]
        )
        mock_file_storage.return_value = mock_fs_instance

        # Execute function
        await Sync_Prompt_Templates(mock_config, "v1")

        # Verify no files were read or written
        mock_fs_instance.read_file.assert_not_called()
        mock_file_open.assert_not_called()

        # Directory should still be created
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    @pytest.mark.asyncio
    @patch("ingenious.utils.conversation_builder.FileStorage")
    @patch("pathlib.Path.mkdir")
    @patch("builtins.open", new_callable=mock_open)
    @patch("ingenious.utils.conversation_builder.logger")
    async def test_sync_prompt_templates_with_logging(
        self, mock_logger, mock_file_open, mock_mkdir, mock_file_storage
    ):
        """Test that proper logging occurs during sync."""
        # Mock config
        mock_config = Mock()
        mock_config.file_storage.revisions.storage_type = "azure"

        # Mock FileStorage instance
        mock_fs_instance = Mock()
        mock_fs_instance.list_files = AsyncMock(return_value=["prompts/v1/template1.jinja"])
        mock_fs_instance.read_file = AsyncMock(return_value="Template content")
        mock_file_storage.return_value = mock_fs_instance

        # Execute function
        await Sync_Prompt_Templates(mock_config, "v1")

        # Verify debug logs were called
        assert mock_logger.debug.call_count == 2
        mock_logger.debug.assert_any_call(
            "Downloading template",
            file_name="template1.jinja",
            source_path="prompts/v1",
        )
        # Note: The second debug call depends on the Path object, so we'll just check the call count
