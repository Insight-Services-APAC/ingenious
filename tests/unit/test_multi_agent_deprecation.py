"""Tests for deprecated conversation flow patterns in multi-agent service.

This module tests that appropriate deprecation warnings are raised when
legacy conversation flow patterns are used.
"""

import sys
import uuid
import warnings
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ingenious.models.chat import ChatRequest, ChatResponse


# Mock openai module to avoid import errors
sys.modules["openai"] = MagicMock()
sys.modules["openai.types"] = MagicMock()
sys.modules["openai.types.chat"] = MagicMock()


class TestDeprecatedPatterns:
    """Test cases for deprecated conversation flow patterns."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock configuration."""
        config = MagicMock()
        config.openai_service_instance = MagicMock()
        config.models = [MagicMock()]
        config.chat_history = MagicMock()
        config.chat_history.memory_path = "/tmp/memory"
        return config

    @pytest.fixture
    def mock_chat_history_repo(self):
        """Create a mock chat history repository."""
        repo = AsyncMock()
        repo.get_thread_messages = AsyncMock(return_value=[])
        return repo

    @pytest.fixture
    def chat_request(self):
        """Create a sample chat request."""
        return ChatRequest(
            user_id="test-user",
            user_prompt="Test message",
            thread_id=str(uuid.uuid4()),
            conversation_flow="test_flow",
            topic="general",
            memory_record=True,
        )

    @pytest.mark.asyncio
    async def test_static_method_deprecation_warning(
        self, mock_config, mock_chat_history_repo, chat_request
    ):
        """Test that deprecation warning is raised for static method pattern."""
        from ingenious.services.chat_services.multi_agent.service import (
            multi_agent_chat_service,
        )

        # Create a mock conversation flow class that simulates static method pattern
        # by raising TypeError when trying to instantiate with parent_multi_agent_chat_service
        class MockStaticFlowClass:
            def __init__(self, *args, **kwargs):
                # Simulate old pattern - doesn't accept parent_multi_agent_chat_service
                if "parent_multi_agent_chat_service" in kwargs:
                    raise TypeError("__init__() got an unexpected keyword argument 'parent_multi_agent_chat_service'")
            
            @staticmethod
            async def get_conversation_response(*args, **kwargs):
                return ("Response text", "Memory summary")

        service = multi_agent_chat_service(
            config=mock_config,
            chat_history_repository=mock_chat_history_repo,
            conversation_flow="test_flow",
        )

        with patch(
            "ingenious.services.chat_services.multi_agent.service.import_class_with_fallback",
            return_value=MockStaticFlowClass,
        ):
            with warnings.catch_warnings(record=True) as w:
                # Enable all warnings
                warnings.simplefilter("always")

                # Call the service method
                await service.get_chat_response(chat_request)

                # Check that at least one DeprecationWarning was raised
                deprecation_warnings = [
                    warning for warning in w if issubclass(warning.category, DeprecationWarning)
                ]
                assert len(deprecation_warnings) > 0, "No deprecation warnings were raised"

                # Check the warning message mentions the pattern being deprecated
                warning_messages = [str(warning.message) for warning in deprecation_warnings]
                assert any(
                    "static method pattern" in msg.lower() for msg in warning_messages
                ), "Warning message should mention static method pattern"

                # Check that migration guide is mentioned
                assert any(
                    "MIGRATION.md" in msg for msg in warning_messages
                ), "Warning should reference MIGRATION.md"

                # Check that v0.3.0 is mentioned
                assert any(
                    "v0.3.0" in msg for msg in warning_messages
                ), "Warning should mention v0.3.0"

    @pytest.mark.asyncio
    async def test_tuple_response_deprecation_warning(
        self, mock_config, mock_chat_history_repo, chat_request
    ):
        """Test that deprecation warning is raised for tuple response format."""
        from ingenious.services.chat_services.multi_agent.service import (
            multi_agent_chat_service,
        )

        # Create a mock conversation flow class that returns a tuple
        class MockTupleFlowClass:
            def __init__(self, *args, **kwargs):
                if "parent_multi_agent_chat_service" in kwargs:
                    raise TypeError("__init__() got an unexpected keyword argument 'parent_multi_agent_chat_service'")
            
            @staticmethod
            async def get_conversation_response(*args, **kwargs):
                return ("Response text", "Memory summary")  # Tuple format

        service = multi_agent_chat_service(
            config=mock_config,
            chat_history_repository=mock_chat_history_repo,
            conversation_flow="test_flow",
        )

        with patch(
            "ingenious.services.chat_services.multi_agent.service.import_class_with_fallback",
            return_value=MockTupleFlowClass,
        ):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")

                await service.get_chat_response(chat_request)

                # Check for deprecation warnings about tuple response
                deprecation_warnings = [
                    warning for warning in w if issubclass(warning.category, DeprecationWarning)
                ]
                assert len(deprecation_warnings) >= 1, "Expected deprecation warnings"

                warning_messages = [str(warning.message) for warning in deprecation_warnings]
                
                # Should have warning about tuple response format
                assert any(
                    "tuple" in msg.lower() for msg in warning_messages
                ), "Should warn about tuple response format"

    @pytest.mark.asyncio
    async def test_new_pattern_no_deprecation_warning(
        self, mock_config, mock_chat_history_repo, chat_request
    ):
        """Test that no deprecation warning is raised for new IConversationFlow pattern."""
        from ingenious.services.chat_services.multi_agent.service import (
            multi_agent_chat_service,
        )

        # Create a mock that simulates IConversationFlow behavior
        class MockNewPatternFlow:
            def __init__(self, parent_multi_agent_chat_service):
                # New pattern accepts parent service
                self.parent = parent_multi_agent_chat_service
                self._config = parent_multi_agent_chat_service.config
                self._chat_service = parent_multi_agent_chat_service
            
            async def get_conversation_response(self, chat_request):
                return ChatResponse(
                    thread_id=chat_request.thread_id,
                    message_id=str(uuid.uuid4()),
                    agent_response="Test response",
                    token_count=10,
                    max_token_count=100,
                    memory_summary="Test memory",
                )

        service = multi_agent_chat_service(
            config=mock_config,
            chat_history_repository=mock_chat_history_repo,
            conversation_flow="test_flow",
        )

        with patch(
            "ingenious.services.chat_services.multi_agent.service.import_class_with_fallback",
            return_value=MockNewPatternFlow,
        ):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")

                response = await service.get_chat_response(chat_request)

                # Check that no deprecation warnings were raised
                deprecation_warnings = [
                    warning for warning in w if issubclass(warning.category, DeprecationWarning)
                ]
                assert (
                    len(deprecation_warnings) == 0
                ), f"No deprecation warnings expected for new pattern, got: {[str(w.message) for w in deprecation_warnings]}"

                # Verify response is correct
                assert isinstance(response, ChatResponse)
                assert response.agent_response == "Test response"

    @pytest.mark.asyncio
    async def test_deprecation_warning_contains_flow_name(
        self, mock_config, mock_chat_history_repo, chat_request
    ):
        """Test that deprecation warning includes the conversation flow name."""
        from ingenious.services.chat_services.multi_agent.service import (
            multi_agent_chat_service,
        )

        chat_request.conversation_flow = "my_custom_flow"

        class MockCustomFlowClass:
            def __init__(self, *args, **kwargs):
                if "parent_multi_agent_chat_service" in kwargs:
                    raise TypeError("__init__() got an unexpected keyword argument 'parent_multi_agent_chat_service'")
            
            @staticmethod
            async def get_conversation_response(*args, **kwargs):
                return ("Response", "Memory")

        service = multi_agent_chat_service(
            config=mock_config,
            chat_history_repository=mock_chat_history_repo,
            conversation_flow="my_custom_flow",
        )

        with patch(
            "ingenious.services.chat_services.multi_agent.service.import_class_with_fallback",
            return_value=MockCustomFlowClass,
        ):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")

                await service.get_chat_response(chat_request)

                deprecation_warnings = [
                    warning for warning in w if issubclass(warning.category, DeprecationWarning)
                ]
                
                warning_messages = [str(warning.message) for warning in deprecation_warnings]
                
                # Should mention the flow name
                assert any(
                    "my_custom_flow" in msg for msg in warning_messages
                ), "Warning should include the conversation flow name"
