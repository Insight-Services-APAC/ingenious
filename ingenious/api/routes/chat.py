"""Chat API routes for conversation endpoints.

This module provides REST endpoints for chat interactions, supporting both
standard request-response and streaming (SSE) modes.
"""

from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from typing_extensions import Annotated

from ingenious.core.structured_logging import get_logger
from ingenious.errors.content_filter_error import ContentFilterError
from ingenious.errors.token_limit_exceeded_error import TokenLimitExceededError
from ingenious.models.chat import ChatRequest, ChatResponse, StreamingChatResponse
from ingenious.models.http_error import HTTPError
from ingenious.services.chat_service import ChatService
from ingenious.services.fastapi_dependencies import (
    get_chat_service,
    get_conditional_security,
)

logger = get_logger(__name__)
router = APIRouter()


@router.post(
    "/chat",
    responses={
        400: {"model": HTTPError, "description": "Bad Request"},
        406: {"model": HTTPError, "description": "Not Acceptable"},
        413: {"model": HTTPError, "description": "Payload Too Large"},
    },
)
async def chat(
    chat_request: ChatRequest,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    username: Annotated[str, Depends(get_conditional_security)],
) -> ChatResponse:
    """Process chat request and return response.

    Args:
        chat_request (ChatRequest): Chat request with message and metadata.
        chat_service (ChatService): Injected chat service instance.
        username (str): Authenticated username.

    Returns:
        ChatResponse: Chat response with assistant message.

    Raises:
        ValidationError: When conversation_flow is not provided.
        ContentFilterError: When content violates filter policies.
        TokenLimitExceededError: When token limit is exceeded.
    """
    from ingenious.errors import ValidationError

    # Set user_id to "unspecified_user" if not provided
    if not chat_request.user_id:
        chat_request.user_id = "unspecified_user"

    # Validate required fields
    if not chat_request.conversation_flow:
        raise ValidationError(
            f"conversation_flow is required but was not provided",
            context={
                "conversation_flow": chat_request.conversation_flow,
                "request_path": "/api/v1/chat",
            },
            user_message="conversation_flow is required",
            recovery_suggestion="Provide a valid conversation_flow in your request",
        )
    
    return await chat_service.get_chat_response(chat_request)


@router.post(
    "/chat/stream",
    responses={
        400: {"model": HTTPError, "description": "Bad Request"},
        406: {"model": HTTPError, "description": "Not Acceptable"},
        413: {"model": HTTPError, "description": "Payload Too Large"},
    },
)
async def chat_stream(
    chat_request: ChatRequest,
    chat_service: Annotated[ChatService, Depends(get_chat_service)],
    username: Annotated[str, Depends(get_conditional_security)],
) -> StreamingResponse:
    """Stream chat responses in real-time using Server-Sent Events.

    Args:
        chat_request (ChatRequest): Chat request with message and metadata.
        chat_service (ChatService): Injected chat service instance.
        username (str): Authenticated username.

    Returns:
        StreamingResponse: SSE stream with chat response chunks.
    """

    async def generate_stream() -> AsyncIterator[str]:
        """Generate SSE stream of chat response chunks.

        Yields:
            str: SSE-formatted data events with chat chunks or errors.
        """
        from ingenious.errors import ValidationError

        try:
            # Set user_id to "unspecified_user" if not provided
            if not chat_request.user_id:
                chat_request.user_id = "unspecified_user"

            # Validate required fields
            if not chat_request.conversation_flow:
                raise ValidationError(
                    f"conversation_flow is required but was not provided",
                    context={
                        "conversation_flow": chat_request.conversation_flow,
                        "request_path": "/api/v1/chat/stream",
                    },
                    user_message="conversation_flow is required",
                    recovery_suggestion="Provide a valid conversation_flow in your request",
                )

            # Enable streaming in request
            chat_request.stream = True

            # Stream the response chunks
            async for chunk in chat_service.get_streaming_chat_response(chat_request):
                streaming_response = StreamingChatResponse(event="data", data=chunk)
                yield f"data: {streaming_response.model_dump_json()}\n\n"

            # Send completion event
            completion_response = StreamingChatResponse(event="done")
            yield f"data: {completion_response.model_dump_json()}\n\n"

        except ContentFilterError as cfe:
            logger.error(
                "Content filter error in streaming",
                conversation_flow=chat_request.conversation_flow,
                error=str(cfe),
                error_code=cfe.error_code,
                correlation_id=cfe.context.correlation_id,
                exc_info=True,
            )
            error_response = StreamingChatResponse(
                event="error", error=cfe.user_message
            )
            yield f"data: {error_response.model_dump_json()}\n\n"

        except TokenLimitExceededError as tle:
            logger.error(
                "Token limit exceeded in streaming",
                conversation_flow=chat_request.conversation_flow,
                error=str(tle),
                error_code=tle.error_code,
                correlation_id=tle.context.correlation_id,
                exc_info=True,
            )
            error_response = StreamingChatResponse(
                event="error", error=tle.user_message
            )
            yield f"data: {error_response.model_dump_json()}\n\n"

        except ValidationError as ve:
            logger.error(
                "Chat streaming request validation error",
                conversation_flow=chat_request.conversation_flow,
                error=str(ve),
                error_code=ve.error_code,
                correlation_id=ve.context.correlation_id,
                exc_info=True,
            )
            error_response = StreamingChatResponse(event="error", error=ve.user_message)
            yield f"data: {error_response.model_dump_json()}\n\n"

        except Exception as e:
            logger.error(
                "Chat streaming request failed",
                conversation_flow=chat_request.conversation_flow if chat_request else None,
                error=str(e),
                exc_info=True,
            )
            error_response = StreamingChatResponse(
                event="error", 
                error="An unexpected error occurred. Please try again or contact support."
            )
            yield f"data: {error_response.model_dump_json()}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
