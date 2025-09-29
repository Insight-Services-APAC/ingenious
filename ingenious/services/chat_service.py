from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, AsyncIterator, Optional, Union

from ingenious.config.main_settings import IngeniousSettings
from ingenious.core.error_handling import operation_context
from ingenious.core.structured_logging import get_logger
from ingenious.db.chat_history_repository import ChatHistoryRepository
from ingenious.errors import (
    ChatServiceError,
)
from ingenious.models.chat import ChatRequest, ChatResponse, ChatResponseChunk
from ingenious.models.config import Config
from ingenious.utils.imports import import_class_with_fallback

logger = get_logger(__name__)


class IChatService(ABC):
    service_class: Any = None

    @abstractmethod
    async def get_chat_response(self, chat_request: ChatRequest) -> ChatResponse:
        pass

    @abstractmethod
    def get_streaming_chat_response(
        self, chat_request: ChatRequest
    ) -> AsyncIterator[ChatResponseChunk]:
        pass


def _resolve_streaming_chunk_size(config: Any, default: int = 100) -> int:
    """Best-effort lookup for streaming chunk size across config variants."""

    def _extract(candidate: Any) -> Optional[int]:
        size = getattr(candidate, "streaming_chunk_size", None)
        return size if isinstance(size, int) and size > 0 else None

    for attr in ("web_configuration", "web"):
        candidate = getattr(config, attr, None)
        if candidate is not None:
            value = _extract(candidate)
            if value is not None:
                return value

    if isinstance(config, Mapping):
        for key in ("web_configuration", "web"):
            if key in config and config[key] is not None:
                value = _extract(config[key])
                if value is not None:
                    return value

    return default


class ChatService(IChatService):
    service_class: Any  # Will be set to instantiated service class

    def __init__(
        self,
        chat_service_type: str,
        chat_history_repository: ChatHistoryRepository,
        conversation_flow: str,
        config: Union[Config, IngeniousSettings],
        revision: str = "dfe19b62-07f1-4cb5-ae9a-561a253e4b04",
    ):
        class_name = f"{chat_service_type.lower()}_chat_service"
        self.config = config
        self.revision = revision

        with operation_context(
            "chat_service_initialization",
            "services.chat",
            error_class=ChatServiceError,
            service_type=chat_service_type,
            conversation_flow=conversation_flow,
        ) as ctx:
            try:
                module_name = (
                    f"services.chat_services.{chat_service_type.lower()}.service"
                )
                service_class = import_class_with_fallback(
                    module_name, class_name, expected_methods=["get_chat_response"]
                )

                ctx.add_metadata(
                    module_name=module_name, class_name=class_name, successful=True
                )

                logger.info(
                    "Chat service class loaded successfully",
                    service_type=chat_service_type,
                    module_name=module_name,
                    class_name=class_name,
                )

            except ImportError as e:
                raise ChatServiceError(
                    "Failed to import chat service module",
                    context={
                        "service_type": chat_service_type,
                        "module_name": module_name,
                        "attempted_modules": [
                            module_name,
                            f"ingenious.services.chat_services.{chat_service_type.lower()}.service",
                        ],
                    },
                    cause=e,
                    recoverable=False,
                    recovery_suggestion="Check if the chat service module exists and is properly installed",
                ) from e

            except AttributeError as e:
                raise ChatServiceError(
                    "Chat service class not found in module",
                    context={
                        "service_type": chat_service_type,
                        "module_name": module_name,
                        "expected_class": class_name,
                    },
                    cause=e,
                    recoverable=False,
                    recovery_suggestion="Ensure the class name matches the service type",
                ) from e

            except Exception as e:
                raise ChatServiceError(
                    "Unexpected error during chat service initialization",
                    context={
                        "service_type": chat_service_type,
                        "module_name": module_name,
                        "class_name": class_name,
                    },
                    cause=e,
                    recovery_suggestion="Check chat service configuration and dependencies",
                ) from e

        self.service_class = service_class(
            config=config,
            chat_history_repository=chat_history_repository,
            conversation_flow=conversation_flow,
        )

    async def get_chat_response(self, chat_request: ChatRequest) -> ChatResponse:
        if not chat_request.conversation_flow:
            raise ValueError(f"conversation_flow not set {chat_request}")
        return await self.service_class.get_chat_response(chat_request)  # type: ignore

    async def get_streaming_chat_response(
        self, chat_request: ChatRequest
    ) -> AsyncIterator[ChatResponseChunk]:
        if not chat_request.conversation_flow:
            raise ValueError(f"conversation_flow not set {chat_request}")

        # Check if the service class supports streaming
        if hasattr(self.service_class, "get_streaming_chat_response"):
            async for chunk in self.service_class.get_streaming_chat_response(
                chat_request
            ):
                yield chunk
        else:
            # Fallback: convert regular response to streaming chunks
            logger.warning(
                "Service class does not support streaming, falling back to chunked response",
                service_class=self.service_class.__class__.__name__,
            )
            response = await self.service_class.get_chat_response(chat_request)

            # Convert response to chunks
            if response.agent_response:
                chunk_size = _resolve_streaming_chunk_size(self.config)
                content = response.agent_response

                for i in range(0, len(content), chunk_size):
                    chunk_content = content[i : i + chunk_size]
                    yield ChatResponseChunk(
                        thread_id=response.thread_id,
                        message_id=response.message_id,
                        chunk_type="content",
                        content=chunk_content,
                        event_type=response.event_type,
                        is_final=False,
                    )

            # Send final chunk with metadata
            yield ChatResponseChunk(
                thread_id=response.thread_id,
                message_id=response.message_id,
                chunk_type="final",
                token_count=response.token_count,
                max_token_count=response.max_token_count,
                topic=response.topic,
                memory_summary=response.memory_summary,
                followup_questions=response.followup_questions,
                event_type=response.event_type,
                is_final=True,
            )
