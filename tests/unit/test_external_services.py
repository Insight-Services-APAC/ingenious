"""
Unit tests for external services.
"""

from unittest.mock import Mock, patch

import pytest
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice

from ingenious.errors.content_filter_error import ContentFilterError
from ingenious.errors.token_limit_exceeded_error import TokenLimitExceededError
from ingenious.external_services.openai_service import OpenAIService


class TestOpenAIService:
    """Test cases for OpenAI service."""

    def test_init_with_azure_config(self):
        """Test OpenAI service initialization with Azure configuration."""
        azure_endpoint = "https://test.openai.azure.com/"
        api_key = "test_key"
        api_version = "2023-03-15-preview"
        model = "gpt-4"

        with patch(
            "ingenious.external_services.openai_service.AzureOpenAI"
        ) as mock_azure:
            mock_client = Mock()
            mock_azure.return_value = mock_client

            service = OpenAIService(azure_endpoint, api_key, api_version, model)

            assert service.client == mock_client
            assert service.model == "gpt-4"
            mock_azure.assert_called_once_with(
                azure_endpoint=azure_endpoint, api_key=api_key, api_version=api_version
            )

    def test_init_with_managed_identity(self):
        """Test OpenAI service initialization with managed identity."""
        azure_endpoint = "https://test.openai.azure.com/"
        api_version = "2023-03-15-preview"
        model = "gpt-4"

        with patch(
            "ingenious.external_services.openai_service.AzureOpenAI"
        ) as mock_azure, patch(
            "ingenious.external_services.openai_service.DefaultAzureCredential"
        ) as mock_credential:
            mock_client = Mock()
            mock_azure.return_value = mock_client
            mock_cred_instance = Mock()
            mock_token = Mock()
            mock_token.token = "test_token"
            mock_cred_instance.get_token.return_value = mock_token
            mock_credential.return_value = mock_cred_instance

            service = OpenAIService(
                azure_endpoint, 
                None, 
                api_version, 
                model, 
                use_managed_identity=True
            )

            assert service.client == mock_client
            assert service.model == "gpt-4"
            mock_credential.assert_called_once()
            # Check that azure_ad_token_provider is a callable
            call_args = mock_azure.call_args
            assert "azure_ad_token_provider" in call_args.kwargs
            assert callable(call_args.kwargs["azure_ad_token_provider"])

    def test_init_managed_identity_without_api_key(self):
        """Test that managed identity works without API key."""
        azure_endpoint = "https://test.openai.azure.com/"
        api_version = "2023-03-15-preview"
        model = "gpt-4"

        with patch(
            "ingenious.external_services.openai_service.AzureOpenAI"
        ) as mock_azure, patch(
            "ingenious.external_services.openai_service.DefaultAzureCredential"
        ) as mock_credential:
            mock_client = Mock()
            mock_azure.return_value = mock_client

            service = OpenAIService(
                azure_endpoint, 
                None, 
                api_version, 
                model, 
                use_managed_identity=True
            )

            assert service.client == mock_client
            mock_credential.assert_called_once()

    def test_init_without_api_key_or_managed_identity_fails(self):
        """Test that initialization fails without API key or managed identity."""
        azure_endpoint = "https://test.openai.azure.com/"
        api_version = "2023-03-15-preview"
        model = "gpt-4"

        with pytest.raises(ValueError, match="API key is required when not using managed identity"):
            OpenAIService(
                azure_endpoint, 
                None, 
                api_version, 
                model, 
                use_managed_identity=False
            )

    def test_init_with_openai_config(self):
        """Test OpenAI service initialization - only Azure is supported."""
        azure_endpoint = "https://test.openai.azure.com/"
        api_key = "test_key"
        api_version = "2023-03-15-preview"
        model = "gpt-4"

        with patch(
            "ingenious.external_services.openai_service.AzureOpenAI"
        ) as mock_azure:
            mock_client = Mock()
            mock_azure.return_value = mock_client

            service = OpenAIService(azure_endpoint, api_key, api_version, model)

            assert service.client == mock_client
            assert service.model == "gpt-4"

    def test_init_missing_config(self):
        """Test OpenAI service initialization with missing configuration."""
        # Test with None parameters - should raise OpenAIError due to missing credentials
        with pytest.raises(Exception):
            OpenAIService(None, None, None, None)

    @pytest.mark.asyncio
    async def test_generate_response_success_azure(self):
        """Test successful response generation with Azure OpenAI."""
        azure_endpoint = "https://test.openai.azure.com/"
        api_key = "test_key"
        api_version = "2023-03-15-preview"
        model = "gpt-4"

        # Mock response
        mock_message = ChatCompletionMessage(role="assistant", content="Test response")
        mock_choice = Choice(index=0, message=mock_message, finish_reason="stop")
        mock_response = ChatCompletion(
            id="test_id",
            choices=[mock_choice],
            created=1234567890,
            model="gpt-4",
            object="chat.completion",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

        with patch(
            "ingenious.external_services.openai_service.AzureOpenAI"
        ) as mock_azure:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_azure.return_value = mock_client

            service = OpenAIService(azure_endpoint, api_key, api_version, model)
            messages = [{"role": "user", "content": "Hello"}]

            response = await service.generate_response(messages)

            assert response.content == "Test response"
            assert response.role == "assistant"

    @pytest.mark.asyncio
    async def test_generate_response_success_openai(self):
        """Test successful response generation with Azure OpenAI."""
        azure_endpoint = "https://test.openai.azure.com/"
        api_key = "test_key"
        api_version = "2023-03-15-preview"
        model = "gpt-4"

        # Mock response
        mock_message = ChatCompletionMessage(role="assistant", content="Test response")
        mock_choice = Choice(index=0, message=mock_message, finish_reason="stop")
        mock_response = ChatCompletion(
            id="test_id",
            choices=[mock_choice],
            created=1234567890,
            model="gpt-4",
            object="chat.completion",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

        with patch(
            "ingenious.external_services.openai_service.AzureOpenAI"
        ) as mock_azure:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_azure.return_value = mock_client

            service = OpenAIService(azure_endpoint, api_key, api_version, model)
            messages = [{"role": "user", "content": "Hello"}]

            response = await service.generate_response(messages)

            assert response.content == "Test response"
            assert response.role == "assistant"

    @pytest.mark.asyncio
    async def test_generate_response_content_filter_error(self):
        """Test response generation with content filter error."""
        azure_endpoint = "https://test.openai.azure.com/"
        api_key = "test_key"
        api_version = "2023-03-15-preview"
        model = "gpt-4"

        with patch(
            "ingenious.external_services.openai_service.AzureOpenAI"
        ) as mock_azure:
            mock_client = Mock()
            from openai import BadRequestError

            mock_error = BadRequestError(
                "Content filter error",
                response=Mock(),
                body={
                    "code": "content_filter",
                    "message": "Content was filtered due to policy violation",
                    "innererror": {"content_filter_result": {}},
                },
            )
            mock_error.code = "content_filter"
            mock_client.chat.completions.create.side_effect = mock_error
            mock_azure.return_value = mock_client

            service = OpenAIService(azure_endpoint, api_key, api_version, model)
            messages = [{"role": "user", "content": "Inappropriate content"}]

            with pytest.raises(ContentFilterError, match="Content was filtered"):
                await service.generate_response(messages)

    @pytest.mark.asyncio
    async def test_generate_response_token_limit_error(self):
        """Test response generation with token limit exceeded error."""
        azure_endpoint = "https://test.openai.azure.com/"
        api_key = "test_key"
        api_version = "2023-03-15-preview"
        model = "gpt-4"

        with patch(
            "ingenious.external_services.openai_service.AzureOpenAI"
        ) as mock_azure:
            mock_client = Mock()
            from openai import BadRequestError

            token_error_msg = "This model's maximum context length is 4096 tokens, however you requested 5000 tokens (4500 in your prompt; 500 for the completion). Please reduce your prompt; or completion length."
            mock_error = BadRequestError(
                token_error_msg, response=Mock(), body={"message": token_error_msg}
            )
            mock_client.chat.completions.create.side_effect = mock_error
            mock_azure.return_value = mock_client

            service = OpenAIService(azure_endpoint, api_key, api_version, model)
            messages = [{"role": "user", "content": "Very long message"}]

            with pytest.raises(TokenLimitExceededError):
                await service.generate_response(messages)

    @pytest.mark.asyncio
    async def test_generate_response_generic_error(self):
        """Test response generation with generic error."""
        azure_endpoint = "https://test.openai.azure.com/"
        api_key = "test_key"
        api_version = "2023-03-15-preview"
        model = "gpt-4"

        with patch(
            "ingenious.external_services.openai_service.AzureOpenAI"
        ) as mock_azure:
            mock_client = Mock()
            from openai import BadRequestError

            mock_error = BadRequestError(
                "An unexpected error occurred",
                response=Mock(),
                body={"message": "An unexpected error occurred"},
            )
            mock_client.chat.completions.create.side_effect = mock_error
            mock_azure.return_value = mock_client

            service = OpenAIService(azure_endpoint, api_key, api_version, model)
            messages = [{"role": "user", "content": "Hello"}]

            with pytest.raises(Exception, match="An unexpected error occurred"):
                await service.generate_response(messages)

    @pytest.mark.asyncio
    async def test_generate_response_with_tools(self):
        """Test response generation with tools."""
        azure_endpoint = "https://test.openai.azure.com/"
        api_key = "test_key"
        api_version = "2023-03-15-preview"
        model = "gpt-4"

        # Mock response
        mock_message = ChatCompletionMessage(role="assistant", content="Test response")
        mock_choice = Choice(index=0, message=mock_message, finish_reason="stop")
        mock_response = ChatCompletion(
            id="test_id",
            choices=[mock_choice],
            created=1234567890,
            model="gpt-4",
            object="chat.completion",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

        with patch(
            "ingenious.external_services.openai_service.AzureOpenAI"
        ) as mock_azure:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_azure.return_value = mock_client

            service = OpenAIService(azure_endpoint, api_key, api_version, model)
            messages = [{"role": "user", "content": "Hello"}]
            tools = [{"type": "function", "function": {"name": "test_tool"}}]

            response = await service.generate_response(messages, tools=tools)

            assert response.content == "Test response"
            assert response.role == "assistant"

    @pytest.mark.asyncio
    async def test_generate_response_empty_response(self):
        """Test response generation with empty response."""
        azure_endpoint = "https://test.openai.azure.com/"
        api_key = "test_key"
        api_version = "2023-03-15-preview"
        model = "gpt-4"

        # Mock response with empty content
        mock_message = ChatCompletionMessage(role="assistant", content="")
        mock_choice = Choice(index=0, message=mock_message, finish_reason="stop")
        mock_response = ChatCompletion(
            id="test_id",
            choices=[mock_choice],
            created=1234567890,
            model="gpt-4",
            object="chat.completion",
            usage={"prompt_tokens": 10, "completion_tokens": 0, "total_tokens": 10},
        )

        with patch(
            "ingenious.external_services.openai_service.AzureOpenAI"
        ) as mock_azure:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_azure.return_value = mock_client

            service = OpenAIService(azure_endpoint, api_key, api_version, model)
            messages = [{"role": "user", "content": "Hello"}]

            response = await service.generate_response(messages)

            assert response.content == ""

    @pytest.mark.asyncio
    async def test_generate_response_no_choices(self):
        """Test response generation with no choices in response."""
        azure_endpoint = "https://test.openai.azure.com/"
        api_key = "test_key"
        api_version = "2023-03-15-preview"
        model = "gpt-4"

        # Mock response with no choices
        mock_response = ChatCompletion(
            id="test_id",
            choices=[],
            created=1234567890,
            model="gpt-4",
            object="chat.completion",
            usage={"prompt_tokens": 10, "completion_tokens": 0, "total_tokens": 10},
        )

        with patch(
            "ingenious.external_services.openai_service.AzureOpenAI"
        ) as mock_azure:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_azure.return_value = mock_client

            service = OpenAIService(azure_endpoint, api_key, api_version, model)
            messages = [{"role": "user", "content": "Hello"}]

            with pytest.raises(IndexError):
                await service.generate_response(messages)

    @pytest.mark.asyncio
    async def test_generate_response_json_mode(self):
        """Test response generation with JSON mode."""
        azure_endpoint = "https://test.openai.azure.com/"
        api_key = "test_key"
        api_version = "2023-03-15-preview"
        model = "gpt-4"

        # Mock response
        mock_message = ChatCompletionMessage(
            role="assistant", content='{"result": "success"}'
        )
        mock_choice = Choice(index=0, message=mock_message, finish_reason="stop")
        mock_response = ChatCompletion(
            id="test_id",
            choices=[mock_choice],
            created=1234567890,
            model="gpt-4",
            object="chat.completion",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

        with patch(
            "ingenious.external_services.openai_service.AzureOpenAI"
        ) as mock_azure:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_azure.return_value = mock_client

            service = OpenAIService(azure_endpoint, api_key, api_version, model)
            messages = [{"role": "user", "content": "Return JSON"}]

            response = await service.generate_response(messages, json_mode=True)

            assert response.content == '{"result": "success"}'
            assert response.role == "assistant"

    @pytest.mark.asyncio
    async def test_generate_response_with_tool_choice(self):
        """Test response generation with tool choice."""
        azure_endpoint = "https://test.openai.azure.com/"
        api_key = "test_key"
        api_version = "2023-03-15-preview"
        model = "gpt-4"

        # Mock response
        mock_message = ChatCompletionMessage(
            role="assistant",
            content=None,
            tool_calls=[
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "test_tool", "arguments": "{}"},
                }
            ],
        )
        mock_choice = Choice(index=0, message=mock_message, finish_reason="tool_calls")
        mock_response = ChatCompletion(
            id="test_id",
            choices=[mock_choice],
            created=1234567890,
            model="gpt-4",
            object="chat.completion",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

        with patch(
            "ingenious.external_services.openai_service.AzureOpenAI"
        ) as mock_azure:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_azure.return_value = mock_client

            service = OpenAIService(azure_endpoint, api_key, api_version, model)
            messages = [{"role": "user", "content": "Use the tool"}]
            tools = [{"type": "function", "function": {"name": "test_tool"}}]

            response = await service.generate_response(
                messages, tools=tools, tool_choice="auto"
            )

            assert response.role == "assistant"
            assert response.tool_calls is not None
