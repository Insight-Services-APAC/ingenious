"""Test agent models."""

import time
from datetime import datetime
from unittest.mock import Mock

import pytest

from ingenious.models.agent import AgentChat


class TestAgentChat:
    """Test AgentChat model."""

    def test_agent_chat_initialization(self):
        """Test AgentChat initialization."""
        chat = AgentChat(
            chat_name="test_chat",
            target_agent_name="assistant",
            source_agent_name="user",
            user_message="Hello",
            system_prompt="You are a helpful assistant"
        )

        assert chat.chat_name == "test_chat"
        assert chat.target_agent_name == "assistant"
        assert chat.source_agent_name == "user"
        assert chat.user_message == "Hello"
        assert chat.system_prompt == "You are a helpful assistant"
        assert chat.identifier is None
        assert chat.chat_response is None
        assert chat.completion_tokens == 0
        assert chat.prompt_tokens == 0
        assert chat.start_time is None
        assert chat.end_time is None

    def test_agent_chat_with_optional_fields(self):
        """Test AgentChat with optional fields."""
        chat = AgentChat(
            chat_name="test_chat",
            target_agent_name="assistant",
            source_agent_name="user",
            user_message="Hello",
            system_prompt="You are a helpful assistant",
            identifier="session-123",
            completion_tokens=50,
            prompt_tokens=10
        )

        assert chat.identifier == "session-123"
        assert chat.completion_tokens == 50
        assert chat.prompt_tokens == 10

    def test_get_execution_time_with_times_set(self):
        """Test execution time calculation when start and end times are set."""
        chat = AgentChat(
            chat_name="test_chat",
            target_agent_name="assistant",
            source_agent_name="user",
            user_message="Hello",
            system_prompt="You are a helpful assistant",
            start_time=1000.0,
            end_time=1005.5
        )

        execution_time = chat.get_execution_time()
        assert execution_time == 5.5

    def test_get_execution_time_without_times_set(self):
        """Test execution time returns 0.0 when times not set."""
        chat = AgentChat(
            chat_name="test_chat",
            target_agent_name="assistant",
            source_agent_name="user",
            user_message="Hello",
            system_prompt="You are a helpful assistant"
        )

        execution_time = chat.get_execution_time()
        assert execution_time == 0.0

    def test_get_execution_time_with_only_start_time(self):
        """Test execution time returns 0.0 when only start time is set."""
        chat = AgentChat(
            chat_name="test_chat",
            target_agent_name="assistant",
            source_agent_name="user",
            user_message="Hello",
            system_prompt="You are a helpful assistant",
            start_time=1000.0
        )

        execution_time = chat.get_execution_time()
        assert execution_time == 0.0

    def test_get_execution_time_formatted(self):
        """Test formatted execution time."""
        chat = AgentChat(
            chat_name="test_chat",
            target_agent_name="assistant",
            source_agent_name="user",
            user_message="Hello",
            system_prompt="You are a helpful assistant",
            start_time=0.0,
            end_time=125.0  # 2 minutes 5 seconds
        )

        formatted_time = chat.get_execution_time_formatted()
        assert formatted_time == "2:05"

    def test_get_execution_time_formatted_hours(self):
        """Test formatted execution time with hours."""
        chat = AgentChat(
            chat_name="test_chat",
            target_agent_name="assistant",
            source_agent_name="user",
            user_message="Hello",
            system_prompt="You are a helpful assistant",
            start_time=0.0,
            end_time=3665.0  # 61 minutes 5 seconds
        )

        formatted_time = chat.get_execution_time_formatted()
        assert formatted_time == "61:05"

    def test_get_start_time_formatted_with_time_set(self):
        """Test formatted start time when set."""
        # Use a known timestamp for consistent testing
        timestamp = 1609459200.0  # 2021-01-01 00:00:00 UTC
        chat = AgentChat(
            chat_name="test_chat",
            target_agent_name="assistant",
            source_agent_name="user",
            user_message="Hello",
            system_prompt="You are a helpful assistant",
            start_time=timestamp
        )

        formatted_time = chat.get_start_time_formatted()
        # The format should be HH:MM:SS
        assert len(formatted_time) == 8
        assert formatted_time.count(':') == 2

    def test_get_start_time_formatted_without_time(self):
        """Test formatted start time returns default when not set."""
        chat = AgentChat(
            chat_name="test_chat",
            target_agent_name="assistant",
            source_agent_name="user",
            user_message="Hello",
            system_prompt="You are a helpful assistant"
        )

        formatted_time = chat.get_start_time_formatted()
        assert formatted_time == "00:00:00"

    def test_get_associated_agent_response_file_name(self):
        """Test agent response filename generation."""
        chat = AgentChat(
            chat_name="test_chat",
            target_agent_name="assistant",
            source_agent_name="user",
            user_message="Hello",
            system_prompt="You are a helpful assistant"
        )

        filename = chat.get_associated_agent_response_file_name("session-123", "complete")

        assert filename == "agent_response_complete_user_assistant_session-123.md"

    def test_get_associated_agent_response_file_name_with_spaces(self):
        """Test agent response filename generation with spaces in identifier."""
        chat = AgentChat(
            chat_name="test_chat",
            target_agent_name="assistant",
            source_agent_name="user",
            user_message="Hello",
            system_prompt="You are a helpful assistant"
        )

        filename = chat.get_associated_agent_response_file_name("  session-123  ", "complete")

        # The strip() should remove leading/trailing spaces
        assert filename == "agent_response_complete_user_assistant_session-123.md"
