"""Unit tests for parallel message saving in multi_agent_chat_service."""

import uuid
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ingenious.models.chat import ChatRequest, ChatResponse
from ingenious.models.message import Message
from ingenious.services.chat_services.multi_agent.service import multi_agent_chat_service


class TestMultiAgentParallelSave:
    """Test cases for parallel message saving functionality."""

    @pytest.mark.asyncio
    async def test_parallel_message_saving_without_memory(self):
        """Test that user and agent messages are saved in parallel when no memory exists."""
        # Setup mocks
        mock_config = Mock()
        mock_config.openai_service_instance = Mock()
        
        mock_chat_history_repo = Mock()
        mock_chat_history_repo.get_thread_messages = AsyncMock(return_value=[])
        mock_chat_history_repo.add_message = AsyncMock(side_effect=["user_msg_id", "agent_msg_id"])
        
        # Create service
        service = multi_agent_chat_service(
            config=mock_config,
            chat_history_repository=mock_chat_history_repo,
            conversation_flow="test_flow"
        )
        
        # Mock the conversation flow execution
        mock_agent_response = ChatResponse(
            thread_id="test_thread",
            message_id="test_message_id",
            agent_response="Test response",
            token_count=100,
            max_token_count=1000,
            memory_summary=""
        )
        
        # Mock the import_class_with_fallback function to return a mock flow
        mock_flow_class = Mock()
        mock_flow_instance = Mock()
        mock_flow_instance.get_conversation_response = AsyncMock(return_value=mock_agent_response)
        mock_flow_class.return_value = mock_flow_instance
        
        with patch("ingenious.services.chat_services.multi_agent.service.import_class_with_fallback", return_value=mock_flow_class):
            # Create request
            request = ChatRequest(
                user_id="test_user",
                thread_id="test_thread",
                user_prompt="Test prompt",
                conversation_flow="test_flow",
                memory_record=True
            )
            
            # Execute
            response = await service.get_chat_response(request)
            
            # Verify parallel execution - add_message should be called exactly twice
            assert mock_chat_history_repo.add_message.call_count == 2
            
            # Verify the messages were created correctly
            calls = mock_chat_history_repo.add_message.call_args_list
            user_msg = calls[0][0][0]
            agent_msg = calls[1][0][0]
            
            assert user_msg.role == "user"
            assert user_msg.content == "Test prompt"
            assert agent_msg.role == "assistant"
            assert agent_msg.content == "Test response"

    @pytest.mark.asyncio
    async def test_parallel_message_saving_with_memory(self):
        """Test that user, agent, and memory messages are saved in parallel."""
        # Setup mocks
        mock_config = Mock()
        mock_config.openai_service_instance = Mock()
        
        mock_chat_history_repo = Mock()
        mock_chat_history_repo.get_thread_messages = AsyncMock(return_value=[])
        mock_chat_history_repo.add_message = AsyncMock(side_effect=["user_msg_id", "agent_msg_id"])
        mock_chat_history_repo.add_memory = AsyncMock(return_value="memory_id")
        
        # Create service
        service = multi_agent_chat_service(
            config=mock_config,
            chat_history_repository=mock_chat_history_repo,
            conversation_flow="test_flow"
        )
        
        # Mock the conversation flow execution
        mock_agent_response = ChatResponse(
            thread_id="test_thread",
            message_id="test_message_id",
            agent_response="Test response",
            token_count=100,
            max_token_count=1000,
            memory_summary="Test memory summary"
        )
        
        # Mock the import_class_with_fallback function to return a mock flow
        mock_flow_class = Mock()
        mock_flow_instance = Mock()
        mock_flow_instance.get_conversation_response = AsyncMock(return_value=mock_agent_response)
        mock_flow_class.return_value = mock_flow_instance
        
        with patch("ingenious.services.chat_services.multi_agent.service.import_class_with_fallback", return_value=mock_flow_class):
            # Create request
            request = ChatRequest(
                user_id="test_user",
                thread_id="test_thread",
                user_prompt="Test prompt",
                conversation_flow="test_flow",
                memory_record=True
            )
            
            # Execute
            response = await service.get_chat_response(request)
            
            # Verify parallel execution - add_message should be called twice, add_memory once
            assert mock_chat_history_repo.add_message.call_count == 2
            assert mock_chat_history_repo.add_memory.call_count == 1
            
            # Verify the memory message was created correctly
            memory_msg = mock_chat_history_repo.add_memory.call_args[0][0]
            assert memory_msg.role == "memory_assistant"
            assert memory_msg.content == "Test memory summary"

    @pytest.mark.asyncio
    async def test_parallel_save_handles_errors_gracefully(self):
        """Test that errors in parallel saves are handled gracefully."""
        # Setup mocks
        mock_config = Mock()
        mock_config.openai_service_instance = Mock()
        
        mock_chat_history_repo = Mock()
        mock_chat_history_repo.get_thread_messages = AsyncMock(return_value=[])
        # Simulate a failure in one of the saves
        mock_chat_history_repo.add_message = AsyncMock(side_effect=Exception("Database error"))
        
        # Create service
        service = multi_agent_chat_service(
            config=mock_config,
            chat_history_repository=mock_chat_history_repo,
            conversation_flow="test_flow"
        )
        
        # Mock the conversation flow execution
        mock_agent_response = ChatResponse(
            thread_id="test_thread",
            message_id="test_message_id",
            agent_response="Test response",
            token_count=100,
            max_token_count=1000,
            memory_summary=""
        )
        
        # Mock the import_class_with_fallback function to return a mock flow
        mock_flow_class = Mock()
        mock_flow_instance = Mock()
        mock_flow_instance.get_conversation_response = AsyncMock(return_value=mock_agent_response)
        mock_flow_class.return_value = mock_flow_instance
        
        with patch("ingenious.services.chat_services.multi_agent.service.import_class_with_fallback", return_value=mock_flow_class):
            # Create request
            request = ChatRequest(
                user_id="test_user",
                thread_id="test_thread",
                user_prompt="Test prompt",
                conversation_flow="test_flow",
                memory_record=True
            )
            
            # Execute - should not raise exception
            response = await service.get_chat_response(request)
            
            # Verify response is still returned despite save failure
            assert response.agent_response == "Test response"

    @pytest.mark.asyncio
    async def test_memory_record_disabled(self):
        """Test that no messages are saved when memory_record is False."""
        # Setup mocks
        mock_config = Mock()
        mock_config.openai_service_instance = Mock()
        
        mock_chat_history_repo = Mock()
        mock_chat_history_repo.get_thread_messages = AsyncMock(return_value=[])
        mock_chat_history_repo.add_message = AsyncMock()
        
        # Create service
        service = multi_agent_chat_service(
            config=mock_config,
            chat_history_repository=mock_chat_history_repo,
            conversation_flow="test_flow"
        )
        
        # Mock the conversation flow execution
        mock_agent_response = ChatResponse(
            thread_id="test_thread",
            message_id="test_message_id",
            agent_response="Test response",
            token_count=100,
            max_token_count=1000,
            memory_summary=""
        )
        
        # Mock the import_class_with_fallback function to return a mock flow
        mock_flow_class = Mock()
        mock_flow_instance = Mock()
        mock_flow_instance.get_conversation_response = AsyncMock(return_value=mock_agent_response)
        mock_flow_class.return_value = mock_flow_instance
        
        with patch("ingenious.services.chat_services.multi_agent.service.import_class_with_fallback", return_value=mock_flow_class):
            # Create request with memory_record=False
            request = ChatRequest(
                user_id="test_user",
                thread_id="test_thread",
                user_prompt="Test prompt",
                conversation_flow="test_flow",
                memory_record=False
            )
            
            # Execute
            response = await service.get_chat_response(request)
            
            # Verify no messages were saved
            assert mock_chat_history_repo.add_message.call_count == 0
