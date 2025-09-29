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
    try:
        # Set user_id to "unspecified_user" if not provided
        if not chat_request.user_id:
            chat_request.user_id = "unspecified_user"

        if not chat_request.conversation_flow:
            raise ValueError(f"conversation_flow not set {chat_request}")
        return await chat_service.get_chat_response(chat_request)
    except ValueError as e:
        logger.error(
            "Chat request validation error",
            conversation_flow=chat_request.conversation_flow,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=str(e))
    except ContentFilterError as cfe:
        logger.error(
            "Content filter error",
            conversation_flow=chat_request.conversation_flow,
            error=str(cfe),
            exc_info=True,
        )
        raise HTTPException(status_code=406, detail=ContentFilterError.DEFAULT_MESSAGE)
    except TokenLimitExceededError as tle:
        logger.error(
            "Token limit exceeded",
            conversation_flow=chat_request.conversation_flow,
            error=str(tle),
            exc_info=True,
        )
        raise HTTPException(
            status_code=413, detail=TokenLimitExceededError.DEFAULT_MESSAGE
        )
    except Exception as e:
        logger.error(
            "Chat request failed",
            conversation_flow=chat_request.conversation_flow if chat_request else None,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e))


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
    """Stream chat responses in real-time using Server-Sent Events (SSE)."""

    async def generate_stream() -> AsyncIterator[str]:
        try:
            # Set user_id to "unspecified_user" if not provided
            if not chat_request.user_id:
                chat_request.user_id = "unspecified_user"

            if not chat_request.conversation_flow:
                raise ValueError(f"conversation_flow not set {chat_request}")

            # Enable streaming in request
            chat_request.stream = True

            # Stream the response chunks
            async for chunk in chat_service.get_streaming_chat_response(chat_request):
                streaming_response = StreamingChatResponse(event="data", data=chunk)
                yield f"data: {streaming_response.model_dump_json()}\n\n"

            # Send completion event
            completion_response = StreamingChatResponse(event="done")
            yield f"data: {completion_response.model_dump_json()}\n\n"

        except ValueError as e:
            logger.error(
                "Chat streaming request validation error",
                conversation_flow=chat_request.conversation_flow,
                error=str(e),
                exc_info=True,
            )
            error_response = StreamingChatResponse(event="error", error=str(e))
            yield f"data: {error_response.model_dump_json()}\n\n"

        except ContentFilterError as cfe:
            logger.error(
                "Content filter error in streaming",
                conversation_flow=chat_request.conversation_flow,
                error=str(cfe),
                exc_info=True,
            )
            error_response = StreamingChatResponse(
                event="error", error=ContentFilterError.DEFAULT_MESSAGE
            )
            yield f"data: {error_response.model_dump_json()}\n\n"

        except TokenLimitExceededError as tle:
            logger.error(
                "Token limit exceeded in streaming",
                conversation_flow=chat_request.conversation_flow,
                error=str(tle),
                exc_info=True,
            )
            error_response = StreamingChatResponse(
                event="error", error=TokenLimitExceededError.DEFAULT_MESSAGE
            )
            yield f"data: {error_response.model_dump_json()}\n\n"

        except Exception as e:
            logger.error(
                "Chat streaming request failed",
                conversation_flow=chat_request.conversation_flow
                if chat_request
                else None,
                error=str(e),
                exc_info=True,
            )
            error_response = StreamingChatResponse(event="error", error=str(e))
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
