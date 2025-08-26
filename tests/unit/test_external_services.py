"""
Unit tests for external services.

This module tests external service integrations, including OpenAI service
which uses Azure OpenAI client builder functions for authentication.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

import pytest
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice

from ingenious.common.enums import AuthenticationMethod
from ingenious.errors.content_filter_error import ContentFilterError
from ingenious.errors.token_limit_exceeded_error import TokenLimitExceededError
from ingenious.external_services.openai_service import OpenAIService

# --------------------------- helpers ---------------------------


def _make_client(
    *, return_value: Any | None = None, side_effect: Exception | None = None
) -> tuple[Any, Mock]:
    """
    Build a minimal client object matching the service's expectations:
      client.chat.completions.create(...)
    """
    create = Mock()
    if side_effect is not None:
        create.side_effect = side_effect
    else:
        create.return_value = return_value

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    return client, create


class TestOpenAIService:
    """Test cases for OpenAI service."""

    def test_init_with_azure_config(self):
        """Test OpenAI service initialization with Azure configuration."""
        azure_endpoint = "https://test.openai.azure.com/"
        api_key = "test_key"
        api_version = "2023-03-15-preview"
        model = "gpt-4.1-nano"

        mock_client = object()
        with patch(
            "ingenious.external_services.openai_service.AzureClientFactory.create_openai_client_from_params",
            return_value=mock_client,
        ) as make_client:
            service = OpenAIService(
                azure_endpoint,
                api_key,
                api_version,
                model,
                authentication_method=AuthenticationMethod.TOKEN,
            )

            assert service.client is mock_client
            assert service.model == model

            # Assert call contract to the factory
            make_client.assert_called_once()
            kwargs = make_client.call_args.kwargs
            assert kwargs["model"] == model
            assert kwargs["base_url"] == azure_endpoint
            assert kwargs["api_version"] == api_version
            # deployment defaults to model when not provided
            assert kwargs["deployment"] == model
            assert kwargs["api_key"] == api_key
            assert kwargs["authentication_method"] == AuthenticationMethod.TOKEN
            assert kwargs["client_id"] is None
            assert kwargs["client_secret"] is None
            assert kwargs["tenant_id"] is None

    def test_init_with_openai_config(self):
        """Test OpenAI service initialization (factory path)."""
        azure_endpoint = "https://test.openai.azure.com/"
        api_key = "test_key"
        api_version = "2023-03-15-preview"
        model = "gpt-4.1-nano"

        mock_client = object()
        with patch(
            "ingenious.external_services.openai_service.AzureClientFactory.create_openai_client_from_params",
            return_value=mock_client,
        ) as make_client:
            service = OpenAIService(
                azure_endpoint,
                api_key,
                api_version,
                model,
                authentication_method=AuthenticationMethod.TOKEN,
            )
            assert service.client is mock_client
            assert service.model == model
            make_client.assert_called_once()

    def test_init_missing_config(self):
        """Test OpenAI service initialization with missing configuration."""
        # Make the factory raise so we don't rely on real packages
        with patch(
            "ingenious.external_services.openai_service.AzureClientFactory.create_openai_client_from_params",
            side_effect=Exception("invalid configuration"),
        ):
            with pytest.raises(Exception, match="invalid configuration"):
                OpenAIService(None, None, None, None)

    # ------------------- behavior / error tests (DI) -------------------

    @pytest.mark.asyncio
    async def test_generate_response_success_azure(self):
        """Test successful response generation (DI client)."""
        mock_message = ChatCompletionMessage(role="assistant", content="Test response")
        mock_choice = Choice(index=0, message=mock_message, finish_reason="stop")
        mock_response = ChatCompletion(
            id="test_id",
            choices=[mock_choice],
            created=1234567890,
            model="gpt-4.1-nano",
            object="chat.completion",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

        client, create = _make_client(return_value=mock_response)
        service = OpenAIService(
            "https://test.openai.azure.com/",
            "k",
            "2023-03-15-preview",
            "gpt-4.1-nano",
            client=client,
        )

        response = await service.generate_response(
            messages=[{"role": "user", "content": "Hello"}]
        )
        assert response.content == "Test response"
        assert response.role == "assistant"
        create.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_response_success_openai(self):
        """Same as Azure path; DI client drives behavior."""
        mock_message = ChatCompletionMessage(role="assistant", content="Test response")
        mock_choice = Choice(index=0, message=mock_message, finish_reason="stop")
        mock_response = ChatCompletion(
            id="test_id",
            choices=[mock_choice],
            created=1234567890,
            model="gpt-4.1-nano",
            object="chat.completion",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

        client, _ = _make_client(return_value=mock_response)
        service = OpenAIService(
            "https://test.openai.azure.com/",
            "k",
            "2023-03-15-preview",
            "gpt-4.1-nano",
            client=client,
        )

        response = await service.generate_response(
            messages=[{"role": "user", "content": "Hello"}]
        )
        assert response.content == "Test response"
        assert response.role == "assistant"

    @pytest.mark.asyncio
    async def test_generate_response_content_filter_error(self):
        """Test response generation with content filter error."""
        from openai import BadRequestError

        token_body = {
            "code": "content_filter",
            "message": "Content was filtered due to policy violation",
            "innererror": {"content_filter_result": {}},
        }
        err = BadRequestError("Content filter error", response=Mock(), body=token_body)
        # set code for our handler
        err.code = "content_filter"

        client, _ = _make_client(side_effect=err)
        service = OpenAIService(
            "https://test.openai.azure.com/",
            "k",
            "2023-03-15-preview",
            "gpt-4.1-nano",
            client=client,
        )

        with pytest.raises(ContentFilterError, match="Content was filtered"):
            await service.generate_response([{"role": "user", "content": "bad"}])

    @pytest.mark.asyncio
    async def test_generate_response_token_limit_error(self):
        """Test response generation with token limit exceeded error."""
        from openai import BadRequestError

        msg = (
            "This model's maximum context length is 4096 tokens, however you requested 5000 tokens "
            "(4500 in your prompt; 500 for the completion). Please reduce your prompt; or completion length."
        )
        err = BadRequestError(msg, response=Mock(), body={"message": msg})

        client, _ = _make_client(side_effect=err)
        service = OpenAIService(
            "https://test.openai.azure.com/",
            "k",
            "2023-03-15-preview",
            "gpt-4.1-nano",
            client=client,
        )

        with pytest.raises(TokenLimitExceededError):
            await service.generate_response([{"role": "user", "content": "long"}])

    @pytest.mark.asyncio
    async def test_generate_response_generic_error(self):
        """Test response generation with generic error."""
        from openai import BadRequestError

        msg = "An unexpected error occurred"
        err = BadRequestError(msg, response=Mock(), body={"message": msg})

        client, _ = _make_client(side_effect=err)
        service = OpenAIService(
            "https://test.openai.azure.com/",
            "k",
            "2023-03-15-preview",
            "gpt-4.1-nano",
            client=client,
        )

        with pytest.raises(Exception, match=msg):
            await service.generate_response([{"role": "user", "content": "Hello"}])

    @pytest.mark.asyncio
    async def test_generate_response_with_tools(self):
        """Test response generation with tools."""
        mock_message = ChatCompletionMessage(role="assistant", content="Test response")
        mock_choice = Choice(index=0, message=mock_message, finish_reason="stop")
        mock_response = ChatCompletion(
            id="test_id",
            choices=[mock_choice],
            created=1234567890,
            model="gpt-4.1-nano",
            object="chat.completion",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

        client, _ = _make_client(return_value=mock_response)
        service = OpenAIService(
            "https://test.openai.azure.com/",
            "k",
            "2023-03-15-preview",
            "gpt-4.1-nano",
            client=client,
        )

        messages = [{"role": "user", "content": "Hello"}]
        tools = [{"type": "function", "function": {"name": "test_tool"}}]

        response = await service.generate_response(messages, tools=tools)
        assert response.content == "Test response"
        assert response.role == "assistant"

    @pytest.mark.asyncio
    async def test_generate_response_empty_response(self):
        """Test response generation with empty assistant content."""
        mock_message = ChatCompletionMessage(role="assistant", content="")
        mock_choice = Choice(index=0, message=mock_message, finish_reason="stop")
        mock_response = ChatCompletion(
            id="test_id",
            choices=[mock_choice],
            created=1234567890,
            model="gpt-4.1-nano",
            object="chat.completion",
            usage={"prompt_tokens": 10, "completion_tokens": 0, "total_tokens": 10},
        )

        client, _ = _make_client(return_value=mock_response)
        service = OpenAIService(
            "https://test.openai.azure.com/",
            "k",
            "2023-03-15-preview",
            "gpt-4.1-nano",
            client=client,
        )

        response = await service.generate_response(
            messages=[{"role": "user", "content": "Hello"}]
        )
        assert response.content == ""

    @pytest.mark.asyncio
    async def test_generate_response_no_choices(self):
        """Test response generation with no choices in response."""
        mock_response = ChatCompletion(
            id="test_id",
            choices=[],
            created=1234567890,
            model="gpt-4.1-nano",
            object="chat.completion",
            usage={"prompt_tokens": 10, "completion_tokens": 0, "total_tokens": 10},
        )

        client, _ = _make_client(return_value=mock_response)
        service = OpenAIService(
            "https://test.openai.azure.com/",
            "k",
            "2023-03-15-preview",
            "gpt-4.1-nano",
            client=client,
        )

        # The service raises a clear RuntimeError for this condition
        with pytest.raises(RuntimeError, match="missing 'choices'"):
            await service.generate_response([{"role": "user", "content": "Hello"}])

    @pytest.mark.asyncio
    async def test_generate_response_json_mode(self):
        """Test response generation with JSON mode."""
        mock_message = ChatCompletionMessage(
            role="assistant", content='{"result": "success"}'
        )
        mock_choice = Choice(index=0, message=mock_message, finish_reason="stop")
        mock_response = ChatCompletion(
            id="test_id",
            choices=[mock_choice],
            created=1234567890,
            model="gpt-4.1-nano",
            object="chat.completion",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

        client, _ = _make_client(return_value=mock_response)
        service = OpenAIService(
            "https://test.openai.azure.com/",
            "k",
            "2023-03-15-preview",
            "gpt-4.1-nano",
            client=client,
        )

        response = await service.generate_response(
            [{"role": "user", "content": "Return JSON"}], json_mode=True
        )
        assert response.content == '{"result": "success"}'
        assert response.role == "assistant"

    @pytest.mark.asyncio
    async def test_generate_response_with_tool_choice(self):
        """Test response generation with tool choice present."""
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
            model="gpt-4.1-nano",
            object="chat.completion",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

        client, _ = _make_client(return_value=mock_response)
        service = OpenAIService(
            "https://test.openai.azure.com/",
            "k",
            "2023-03-15-preview",
            "gpt-4.1-nano",
            client=client,
        )

        messages = [{"role": "user", "content": "Use the tool"}]
        tools = [{"type": "function", "function": {"name": "test_tool"}}]

        response = await service.generate_response(
            messages, tools=tools, tool_choice="auto"
        )
        assert response.role == "assistant"
        assert response.tool_calls is not None
