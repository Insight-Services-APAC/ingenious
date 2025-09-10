# Insight_Ingenious/ingenious/services/chat_service.py
"""Chat service façade and streaming delegator.

Provide a thin façade that dynamically loads the configured chat backend and
exposes both non‑streaming (`get_chat_response`) and streaming
(`get_streaming_chat_response`) interfaces. When a backend does not support
native streaming, this façade preserves legacy, configurable chunking behavior.
After streaming finishes, it performs best‑effort persistence of user/assistant
messages and memory (when enabled) without affecting already‑sent data.

Usage:
- Construct via DI with a `chat_service_type`, repository, flow, and config.
- Call `get_chat_response` for one‑shot replies, or
  `get_streaming_chat_response` to iterate `ChatResponseChunk` items.

Key entry points:
- ChatService.get_chat_response
- ChatService.get_streaming_chat_response
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from types import SimpleNamespace
from typing import Any, AsyncIterator

from ingenious.config.main_settings import IngeniousSettings
from ingenious.core.structured_logging import get_logger
from ingenious.db.chat_history_repository import ChatHistoryRepository
from ingenious.models.chat import ChatRequest, ChatResponse, ChatResponseChunk
from ingenious.models.config import Config

# ---------------------------------------------------------------------------
# Importer wiring
# Expose `import_class_with_fallback` at module scope so tests can monkeypatch.
# ---------------------------------------------------------------------------
try:
    # Real helper provided by the project; tests patch this symbol on this module.
    from ingenious.utils.imports import (  # type: ignore[import-untyped]
        import_class_with_fallback as import_class_with_fallback,
    )
except Exception:  # pragma: no cover - ultra defensive
    def import_class_with_fallback(
        module_name: str, class_name: str, *, expected_methods: list[str]
    ) -> Any:
        """Fallback when the real imports helper is unavailable.

        Args:
            module_name: Dotted path to import.
            class_name: Class name to resolve.
            expected_methods: Methods that the class must expose.

        Raises:
            ImportError: Always, indicating the helper isn't available.
        """
        raise ImportError("ingenious.utils.imports not available")


def _call_importer(
    module_name: str, class_name: str, *, expected_methods: list[str]
) -> Any:
    """Resolve and call the importer function at *call time*.

    Tries the source module first (so tests that patch
    `ingenious.utils.imports.import_class_with_fallback` are honored), and
    falls back to the module-level alias on this module (so tests that patch
    `ingenious.services.chat_service.import_class_with_fallback` still work).
    """
    # 1) Prefer the function on the source module (dynamic lookup)
    try:
        from importlib import import_module

        imports_mod = import_module("ingenious.utils.imports")
        importer = getattr(imports_mod, "import_class_with_fallback")
        return importer(
            module_name, class_name, expected_methods=expected_methods
        )
    except Exception:
        # 2) Fallback to the alias captured on this module (also patchable)
        return import_class_with_fallback(
            module_name, class_name, expected_methods=expected_methods
        )

# Base error + a small compatibility wrapper ensuring `.context` is a dict.
try:
    from ingenious.errors import ChatServiceError as _BaseChatServiceError
except Exception:  # pragma: no cover - test environments may vary
    class _BaseChatServiceError(Exception):  # type: ignore[override]
        """Fallback base when error module is unavailable."""

        def __init__(self, message: str, **_: Any) -> None:
            super().__init__(message)


class ChatServiceInitError(_BaseChatServiceError):
    """Compatibility subclass that guarantees a dict-like `.context`.

    Why:
        Some tests index `err.context["service_type"]`. Upstream implementations
        sometimes expose an `ErrorContext` object instead. This wrapper ensures
        `.context` is always a plain `dict` while remaining catchable as the
        base `ChatServiceError`.
    """

    def __init__(
        self,
        message: str,
        *,
        context: dict[str, Any] | None = None,
        cause: Exception | None = None,
        recoverable: bool | None = None,
        recovery_suggestion: str | None = None,
    ) -> None:
        """Initialize the error with predictable, dict-shaped metadata."""
        # Intentionally avoid calling the upstream initializer to keep the shape
        # predictable for tests (no ErrorContext wrapping).
        Exception.__init__(self, message)
        self.message: str = message
        self.context: dict[str, Any] = context or {}
        self.cause: Exception | None = cause
        self.recoverable: bool | None = recoverable
        self.recovery_suggestion: str | None = recovery_suggestion
        # Provide a common alias many loggers expect.
        self.metadata: dict[str, Any] = self.context


# Custom ImportError type from the importer module (if provided)
try:
    from ingenious.utils.imports import (  # type: ignore[import-untyped]
        ImportError as ImporterError,
    )
except Exception:  # pragma: no cover - defensive fallback
    class ImporterError(Exception):  # type: ignore[override]
        """Fallback alias for the import helper's custom ImportError."""


logger = get_logger(__name__)

DEFAULT_REVISION = "dfe19b62-07f1-4cb5-ae9a-561a253e4b04"
DEFAULT_STREAMING_CHUNK_SIZE = 100
SERVICE_MODULE_TEMPLATE = "services.chat_services.{service}.service"
EXPECTED_METHODS = ["get_chat_response"]
FALLBACK_CONTENT_TYPES = {"content", "delta"}


class IChatService(ABC):
    """Interface for chat services.

    Defines the minimal surface required by callers. Concrete implementations
    are dynamically loaded based on `chat_service_type` at runtime.
    """

    @abstractmethod
    async def get_chat_response(self, chat_request: ChatRequest) -> ChatResponse:
        """Return a complete, non‑streaming chat response.

        Why:
            Enables callers to obtain the full assistant reply in one call when
            streaming is unnecessary or unsupported downstream.

        Args:
            chat_request: Structured request with prompts and context.

        Returns:
            A `ChatResponse` with fields such as `agent_response` and tokens.
        """
        raise NotImplementedError

    @abstractmethod
    def get_streaming_chat_response(
        self, chat_request: ChatRequest
    ) -> AsyncIterator[ChatResponseChunk]:
        """Yield a streaming chat response as an async iterator of chunks.

        Why:
            Supports progressive delivery and UI interactivity. Implementations
            can provide native streaming; otherwise the façade provides a
            compatible, chunked fallback.

        Args:
            chat_request: Structured request with prompts and context.

        Yields:
            `ChatResponseChunk` items carrying partial or final data.
        """
        raise NotImplementedError


class ChatService(IChatService):
    """Main chat service façade that delegates to specific implementations.

    Loads the concrete chat backend at construction and delegates both one‑shot
    and streaming requests. When streaming is not supported by the backend, the
    class emits chunks using a configurable chunk size and later persists
    messages and memory (if enabled).
    """

    service_class: Any  # Instance of the dynamically loaded backend class.

    def __init__(
        self,
        chat_service_type: str,
        chat_history_repository: ChatHistoryRepository,
        conversation_flow: str,
        config: Config | IngeniousSettings,
        revision: str = DEFAULT_REVISION,
    ) -> None:
        """Construct the façade and instantiate the underlying service.

        Why:
            Defer backend choice to configuration while keeping a stable API.
            Centralizes error handling and logging for backend resolution.

        Args:
            chat_service_type: Key identifying the backend implementation.
            chat_history_repository: Repository used for history & memory writes.
            conversation_flow: Name of the flow (trace/debug context).
            config: Application/runtime configuration object.
            revision: Build or code revision identifier used for tracing.

        Raises:
            ChatServiceInitError: When the backend class cannot be imported/found.
        """
        class_name = f"{chat_service_type.lower()}_chat_service"
        self.config = config
        self.revision = revision
        self.chat_history_repository = chat_history_repository

        module_name = SERVICE_MODULE_TEMPLATE.format(service=chat_service_type.lower())

        try:
            # Resolve the importer at call time so test monkeypatches are honored.
            service_class = _call_importer(
                module_name, class_name, expected_methods=EXPECTED_METHODS
            )
            logger.info(
                "Chat service class loaded successfully",
                service_type=chat_service_type,
                module_name=module_name,
                class_name=class_name,
            )
        except (ImporterError, ImportError) as e:
            # Map precisely to the error the tests expect and keep a **dict** context.
            raise ChatServiceInitError(
                "Failed to import chat service module",
                context={
                    "service_type": chat_service_type,
                    "module_name": module_name,
                    "attempted_modules": [
                        module_name,
                        (
                            "ingenious.services.chat_services."
                            f"{chat_service_type.lower()}.service"
                        ),
                    ],
                },
                cause=e,
                recoverable=False,
                recovery_suggestion=(
                    "Check if the chat service module exists and is properly installed"
                ),
            ) from e
        except AttributeError as e:
            raise ChatServiceInitError(
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
            raise ChatServiceInitError(
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
        """Return a one‑shot `ChatResponse` (non‑streaming).

        Why:
            Provides a synchronous‑style API that returns the full message when
            streaming is not required by the caller.

        Args:
            chat_request: Structured request with prompts and context.

        Returns:
            A `ChatResponse` object.

        Raises:
            ValueError: If `conversation_flow` is not set on the request.
        """
        if not chat_request.conversation_flow:
            raise ValueError(f"conversation_flow not set {chat_request}")
        return await self.service_class.get_chat_response(chat_request)

    async def get_streaming_chat_response(
        self, chat_request: ChatRequest
    ) -> AsyncIterator[ChatResponseChunk]:
        """Yield `ChatResponseChunk` items in real time.

        Why:
            Delegates to the backend if it supports streaming, forwarding chunks
            verbatim to avoid reordering. Otherwise, preserves the original
            system's chunked fallback semantics, including metadata fields.

        Args:
            chat_request: Structured request with prompts and context.

        Yields:
            Streaming `ChatResponseChunk` items.

        Raises:
            ValueError: If `conversation_flow` is not set on the request.
        """
        if not chat_request.conversation_flow:
            raise ValueError(f"conversation_flow not set {chat_request}")

        # Mark as streaming so downstream (multi-agent) skips premature persistence.
        chat_request.stream = True

        default_thread_id = chat_request.thread_id or str(uuid.uuid4())
        default_message_id = str(uuid.uuid4())

        collected_content_parts: list[str] = []
        final_memory_summary: str | None = None
        observed_thread_id: str | None = None
        observed_message_id: str | None = None

        try:
            # Delegate to the backend service (which may implement native streaming)
            if hasattr(self.service_class, "get_streaming_chat_response"):
                async for chunk in self.service_class.get_streaming_chat_response(
                    chat_request
                ):
                    # Track IDs for post-stream persistence
                    observed_thread_id = chunk.thread_id or observed_thread_id
                    observed_message_id = chunk.message_id or observed_message_id

                    # Accumulate textual content for history
                    if (
                        (chunk.chunk_type in FALLBACK_CONTENT_TYPES) or chunk.is_final
                    ) and chunk.content:
                        collected_content_parts.append(chunk.content)

                    # Capture memory summary if present
                    if chunk.memory_summary:
                        final_memory_summary = chunk.memory_summary

                    # Emit verbatim to preserve backend semantics
                    yield chunk
            else:
                # Fallback: convert regular response to streaming chunks (legacy compatible)
                logger.warning(
                    "Service class does not support streaming, falling back to "
                    "chunked response",
                    service_class=self.service_class.__class__.__name__,
                )

                response = await self.service_class.get_chat_response(chat_request)
                text = response.agent_response or ""
                event_type = response.event_type
                thread_id = response.thread_id or default_thread_id
                message_id = response.message_id or default_message_id
                chunk_size = self._get_streaming_chunk_size()

                # Convert response to chunks with configurable size
                if text:
                    for i in range(0, len(text), chunk_size):
                        chunk_content = text[i : i + chunk_size]
                        yield ChatResponseChunk(
                            thread_id=thread_id,
                            message_id=message_id,
                            chunk_type="content",
                            content=chunk_content,
                            event_type=event_type,
                            is_final=False,
                        )

                # Send final chunk with metadata (preserve original fields)
                yield ChatResponseChunk(
                    thread_id=thread_id,
                    message_id=message_id,
                    chunk_type="final",
                    token_count=response.token_count,
                    max_token_count=response.max_token_count,
                    topic=response.topic,
                    memory_summary=response.memory_summary,
                    followup_questions=response.followup_questions,
                    event_type=event_type,
                    is_final=True,
                )

                # Collect for persistence
                if text:
                    collected_content_parts.append(text)
                final_memory_summary = response.memory_summary
                observed_thread_id = thread_id
                observed_message_id = message_id

        finally:
            # Best-effort persistence after the stream completes
            try:
                if (
                    getattr(chat_request, "memory_record", True)
                    and chat_request.user_id
                    and self.chat_history_repository
                ):
                    thread_id = observed_thread_id or default_thread_id
                    assistant_text = "".join(collected_content_parts).strip()

                    # Persist objects with attribute access (tests expect .role/.content)
                    user_msg = SimpleNamespace(
                        user_id=chat_request.user_id,
                        thread_id=thread_id,
                        role="user",
                        content=chat_request.user_prompt,
                    )
                    await self.chat_history_repository.add_message(user_msg)

                    if assistant_text:
                        asst_msg = SimpleNamespace(
                            user_id=chat_request.user_id,
                            thread_id=thread_id,
                            role="assistant",
                            content=assistant_text,
                        )
                        await self.chat_history_repository.add_message(asst_msg)

                    if final_memory_summary:
                        mem_msg = SimpleNamespace(
                            user_id=chat_request.user_id,
                            thread_id=thread_id,
                            role="memory_assistant",
                            content=final_memory_summary,
                        )
                        await self.chat_history_repository.add_memory(mem_msg)
            except Exception as e:  # noqa: BLE001 - never break the stream on persistence
                logger.error(
                    "Post-stream persistence failed",
                    error=str(e),
                    exc_info=True,
                )

    def _get_streaming_chunk_size(self) -> int:
        """Return the configured streaming chunk size with a safe default.

        Why:
            The original system exposed `config.web.streaming_chunk_size`. This
            helper tolerates both dict-like and attr-like `config.web` layouts
            and falls back to `DEFAULT_STREAMING_CHUNK_SIZE`. Non-positive values
            are treated as invalid and fall back to the default as well.

        Returns:
            The chunk size as a positive integer.
        """
        try:
            web_cfg = getattr(self.config, "web", None)
            if isinstance(web_cfg, dict):
                val = int(
                    web_cfg.get("streaming_chunk_size", DEFAULT_STREAMING_CHUNK_SIZE)
                )
            else:
                val = int(
                    getattr(
                        web_cfg, "streaming_chunk_size", DEFAULT_STREAMING_CHUNK_SIZE
                    )
                )
            return DEFAULT_STREAMING_CHUNK_SIZE if val <= 0 else val
        except (TypeError, ValueError, AttributeError):
            return DEFAULT_STREAMING_CHUNK_SIZE
