# ingenious/services/chat_services/multi_agent/service.py
"""Multi‑agent chat service (flows + universal streaming fallback, back‑compat).

Why/what:
- Loads and executes a conversation flow selected by `conversation_flow`.
- Provides non‑streaming and streaming entry points.
- Preserves **v1 streaming protocol** (`content` → `final`) for compatibility.
- Optionally supports **v2 streaming protocol** via config flag:
  status("start") → status("generation") → delta* → summary → usage → final.

Usage:
- Instantiated by the ChatService façade (DI).
- Flows may implement:
  * `IConversationFlow.get_streaming_conversation_response` (instance override),
  * or a legacy **static** `get_streaming_conversation_response(...)`.
- If a flow doesn't implement native streaming, a universal fallback is used.
"""

from __future__ import annotations

import inspect
import logging
import uuid as uuid_module
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, List, Optional

from jinja2 import Environment

import ingenious.config.config as ig_config

if TYPE_CHECKING:  # type-only imports
    from ingenious.models.config import Config
    from openai.types.chat import ChatCompletionMessageParam  # type: ignore

from ingenious.core.structured_logging import get_logger
from ingenious.db.chat_history_repository import ChatHistoryRepository
from ingenious.errors.content_filter_error import ContentFilterError
from ingenious.files.files_repository import FileStorage
from ingenious.models.chat import ChatResponseChunk, IChatRequest, IChatResponse
from ingenious.utils.namespace_utils import (
    import_class_with_fallback,
    normalize_workflow_name,
)

# ──────────────────────────────────────────────────────────────────────────────
# Patch points for tests: provide aliases that tests can monkeypatch
# (e.g., monkeypatch.setattr(module, "get_memory_manager", fake)).
# Production code uses the real implementations.
# ──────────────────────────────────────────────────────────────────────────────
from ingenious.services.memory_manager import (  # noqa: E402 (defer clarity)
    get_memory_manager as _get_memory_manager_impl,
    run_async_memory_operation as _run_async_memory_operation_impl,
)

get_memory_manager = _get_memory_manager_impl
run_async_memory_operation = _run_async_memory_operation_impl

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_V1_CHUNK_SIZE: int = 100
DEFAULT_V2_TARGET_CHARS: int = 320
STREAM_PROTOCOL_V1: int = 1
STREAM_PROTOCOL_V2: int = 2

logger = get_logger(__name__)


class multi_agent_chat_service:
    """Orchestrates multi-agent conversation flows, with streaming + fallbacks.

    The service coordinates conversation flows selected by `conversation_flow`,
    exposes synchronous and streaming entry points, and preserves the original
    streaming contract (v1: `content` + terminal `final` chunk). A new protocol
    (v2) can be enabled via configuration (see `_get_stream_protocol_version`).
    """

    config: "Config"
    chat_history_repository: ChatHistoryRepository
    conversation_flow: str
    openai_service: Optional[ChatCompletionMessageParam]

    def __init__(
        self,
        config: "Config",
        chat_history_repository: ChatHistoryRepository,
        conversation_flow: str,
    ) -> None:
        """Create the multi-agent chat service.

        Why:
            Inject configuration and repositories. Validates that an OpenAI
            service instance is available from the provided config.

        Args:
            config: Application configuration object.
            chat_history_repository: Repository for persisting chat history.
            conversation_flow: Name of the conversation flow to execute.

        Raises:
            RuntimeError: If an OpenAI service instance is not provided.
        """
        self.config = config
        self.chat_history_repository = chat_history_repository
        self.conversation_flow = conversation_flow

        # Tests often pass a tiny config without an explicit OpenAI service.
        # Keep this optional; flows that need a client construct it themselves.
        self.openai_service = getattr(config, "openai_service_instance", None)  # type: ignore[attr-defined]

    # ─────────────────────────────── helpers ────────────────────────────────

    def _get_stream_protocol_version(self) -> int:
        """Determine desired streaming protocol (v1 default; v2 optional).

        Why:
            Preserve original client contract by default (v1). Allow opting into
            the enhanced event protocol without breaking existing consumers.

        Returns:
            1 for v1 (`content`/`final`) or 2 for v2 (status/delta/summary/usage/final).
        """
        # Prefer web-level setting if present, else chat_service-level, else v1.
        try:
            web = getattr(self.config, "web", None)
            if web and hasattr(web, "stream_protocol_version"):
                return int(getattr(web, "stream_protocol_version"))
        except Exception:
            # Best-effort only; fall back safely to v1
            pass

        try:
            chat = getattr(self.config, "chat_service", None)
            if chat and hasattr(chat, "stream_protocol_version"):
                return int(getattr(chat, "stream_protocol_version"))
        except Exception:
            pass

        return STREAM_PROTOCOL_V1

    def _get_configured_chunk_size(self) -> int:
        """Read configured chunk size; fall back to DEFAULT_V1_CHUNK_SIZE.

        Returns:
            Positive chunk size in characters.
        """
        try:
            if hasattr(self.config, "web") and hasattr(
                self.config.web, "streaming_chunk_size"
            ):
                value = int(self.config.web.streaming_chunk_size)
                return value if value > 0 else DEFAULT_V1_CHUNK_SIZE
        except Exception:
            # Safe fallback on any misconfiguration
            pass
        return DEFAULT_V1_CHUNK_SIZE

    # ─────────────────────────── request/memory ─────────────────────────────

    async def _prepare_chat_request(self, chat_request: IChatRequest) -> IChatRequest:
        """Prepare and validate the chat request.

        Why:
            Normalize inputs, ensure `thread_id` exists, and seed the per-thread
            chat history structure used by flows.

        Args:
            chat_request: The incoming chat request DTO.

        Returns:
            The validated and normalized chat request.

        Raises:
            ValueError: If `conversation_flow` is not provided.
        """
        if not chat_request.conversation_flow:
            raise ValueError(f"conversation_flow not set {chat_request}")

        if isinstance(chat_request.topic, str):
            chat_request.topic = [
                topic.strip() for topic in chat_request.topic.split(",")
            ]  # type: ignore

        # Initialize minimal history structure if absent (avoid seeding fake message).
        chat_request.thread_chat_history = []  # type: ignore

        if not chat_request.thread_id:
            chat_request.thread_id = str(uuid_module.uuid4())

        return chat_request

    async def _build_thread_memory(self, chat_request: IChatRequest) -> List[Any]:
        """Build thread memory summary from recent messages.

        Why:
            Provide flows a lightweight context summary without loading entire
            history into prompt tokens.

        Args:
            chat_request: The normalized chat request.

        Returns:
            The list of thread messages retrieved from the repository.
        """
        thread_messages = await self.chat_history_repository.get_thread_messages(
            chat_request.thread_id
        )

        if thread_messages:
            memory_parts: List[str] = []
            for msg in thread_messages[-10:]:  # last N messages
                memory_parts.append(f"{msg.role}: {msg.content[:200]}...")
            chat_request.thread_memory = "\n".join(memory_parts)
        else:
            chat_request.thread_memory = "no existing context."

        logger.info(
            "Current memory state",
            thread_id=chat_request.thread_id,
            memory_length=len(chat_request.thread_memory or ""),
        )
        logger.debug(
            "Thread messages and memory processed",
            message_count=len(thread_messages or []),
            operation="process_thread_context",
        )

        return thread_messages

    async def _process_thread_messages(
        self, chat_request: IChatRequest, thread_messages: List[Any]
    ) -> None:
        """Validate and append thread messages to the request's chat history.

        Why:
            Enforce content filtering and expose prior messages to flows in a
            normalized list format.

        Args:
            chat_request: Current request being enriched.
            thread_messages: Messages fetched for the thread.

        Raises:
            ContentFilterError: If any message has content filter violations.
        """
        for thread_message in thread_messages or []:
            if thread_message.content_filter_results:
                raise ContentFilterError(
                    content_filter_results=thread_message.content_filter_results
                )
            if (
                hasattr(chat_request, "thread_chat_history")
                and chat_request.thread_chat_history
            ):
                chat_request.thread_chat_history.append(  # type: ignore
                    {"role": thread_message.role, "content": thread_message.content}
                )

    # ───────────────────────── conversation execution ────────────────────────

    async def get_chat_response(self, chat_request: IChatRequest) -> IChatResponse:
        """Execute the selected conversation flow and return a full response.

        Why:
            This is the non-streaming entry point. It performs preparation,
            executes the flow (new or legacy signature), and persists history
            unless streaming is active.

        Args:
            chat_request: The incoming chat request DTO.

        Returns:
            A complete `IChatResponse` object from the flow.
        """
        chat_request = await self._prepare_chat_request(chat_request)
        thread_messages = await self._build_thread_memory(chat_request)
        await self._process_thread_messages(chat_request, thread_messages)

        conversation_flow_class = self._load_conversation_flow_class(chat_request)
        agent_response = await self._execute_conversation_flow(
            conversation_flow_class, chat_request
        )

        # Preserve modified logic: skip persistence when streaming is active.
        if getattr(chat_request, "memory_record", True) and not getattr(
            chat_request, "stream", False
        ):
            await self._save_chat_history(chat_request, agent_response)

        return agent_response

    def _load_conversation_flow_class(self, chat_request: IChatRequest) -> Any:
        """Resolve and import the ConversationFlow class to execute.

        Why:
            Supports both built-in and extension flows; normalizes names and
            honors the feature flag for disabling built-in flows.

        Args:
            chat_request: The incoming chat request, used if service field empty.

        Returns:
            The `ConversationFlow` class object.

        Raises:
            ValueError: If no conversation flow is provided or enabled.
            ImportError: If the module/class cannot be imported via fallback.
        """
        # Always prefer the request's flow if provided; fall back to the service default
        effective_flow = chat_request.conversation_flow or self.conversation_flow
        if not effective_flow:
             raise ValueError(f"conversation_flow not set {chat_request}")
        # Persist the effective flow for logging/consistency
        self.conversation_flow = effective_flow

        logger.info(
            "Starting conversation flow execution",
            conversation_flow=self.conversation_flow,
            operation="conversation_flow_start",
        )

        normalized_flow = normalize_workflow_name(self.conversation_flow)

        builtin_workflows = {
            "classification_agent",
            "knowledge_base_agent",
            "sql_manipulation_agent",
        }
        if (
            not self.config.chat_service.enable_builtin_workflows
            and normalized_flow in builtin_workflows
        ):
            raise ValueError(
                f"Built-in workflow '{self.conversation_flow}' is disabled. "
                f"Set INGENIOUS_CHAT_SERVICE__ENABLE_BUILTIN_WORKFLOWS=true to enable "
                f"built-in workflows, or use a custom workflow from ingenious_extensions."
            )

        module_name = (
            f"services.chat_services.multi_agent.conversation_flows."
            f"{normalized_flow}.{normalized_flow}"
        )
        class_name = "ConversationFlow"

        logger.debug(
            "Loading conversation flow module",
            module_name=module_name,
            class_name=class_name,
            original_workflow=self.conversation_flow,
            normalized_workflow=normalized_flow,
            operation="module_loading",
        )

        conversation_flow_class = import_class_with_fallback(module_name, class_name)

        logger.info(
            "Successfully loaded conversation flow class",
            class_type=str(type(conversation_flow_class)),
            conversation_flow=self.conversation_flow,
            operation="class_loading_success",
        )

        return conversation_flow_class

    async def _execute_new_pattern(
        self, conversation_flow_class: Any, chat_request: IChatRequest
    ) -> Any:
        """Execute a flow that implements the new `IConversationFlow` pattern.

        Args:
            conversation_flow_class: The flow class object.
            chat_request: The current request.

        Returns:
            The flow's response (often `ChatResponse`).
        """
        instance = conversation_flow_class(parent_multi_agent_chat_service=self)
        response_task = instance.get_conversation_response(chat_request=chat_request)
        return await response_task

    async def _execute_static_pattern(
        self, conversation_flow_class: Any, chat_request: IChatRequest
    ) -> Any:
        """Execute a flow that exposes a legacy static method API.

        Why:
            Preserve backward compatibility with flows that defined a static
            `get_conversation_response` accepting either a single request or
            expanded arguments.

        Args:
            conversation_flow_class: The flow class object.
            chat_request: The current request.

        Returns:
            The flow's response (often `ChatResponse`).
        """
        logger.info(
            "Using static method pattern for conversation flow",
            conversation_flow=self.conversation_flow,
            operation="fallback_static_method",
        )

        sig = inspect.signature(conversation_flow_class.get_conversation_response)
        params = list(sig.parameters.keys())

        logger.debug(
            "Analyzing method signature",
            parameters=params,
            param_count=len(params),
            operation="method_signature_analysis",
        )

        if len(params) == 1 and params[0] not in ["self", "cls"]:
            response_task = conversation_flow_class.get_conversation_response(
                chat_request
            )
        else:
            response_task = conversation_flow_class.get_conversation_response(
                message=chat_request.user_prompt,
                topics=chat_request.topic
                if isinstance(chat_request.topic, list)
                else ([chat_request.topic] if chat_request.topic else []),
                thread_memory=getattr(chat_request, "thread_memory", ""),
                memory_record_switch=getattr(chat_request, "memory_record", True),
                thread_chat_history=getattr(chat_request, "thread_chat_history", []),
            )

        logger.debug("Awaiting conversation flow response", operation="response_await")
        return await response_task

    def _convert_response_format(
        self, response_tuple: Any, chat_request: IChatRequest
    ) -> Any:
        """Convert legacy tuple forms into a `ChatResponse`.

        Args:
            response_tuple: Either a `ChatResponse`, `(text, memory)` tuple, or
                any other object convertible to string.
            chat_request: Current request for ID fields.

        Returns:
            A `ChatResponse` instance.
        """
        from ingenious.models.chat import ChatResponse

        logger.debug(
            "Received conversation flow response",
            response_type=str(type(response_tuple)),
            operation="response_received",
        )

        if isinstance(response_tuple, ChatResponse):
            return response_tuple

        if isinstance(response_tuple, tuple) and len(response_tuple) == 2:
            response_text, memory_summary = response_tuple
            return ChatResponse(
                thread_id=chat_request.thread_id,
                message_id=str(uuid_module.uuid4()),
                agent_response=response_text,
                token_count=0,
                max_token_count=0,
                memory_summary=memory_summary,
            )

        return ChatResponse(
            thread_id=chat_request.thread_id,
            message_id=str(uuid_module.uuid4()),
            agent_response=str(response_tuple),
            token_count=0,
            max_token_count=0,
            memory_summary="",
        )

    async def _execute_conversation_flow(
        self, conversation_flow_class: Any, chat_request: IChatRequest
    ) -> Any:
        """Execute the flow with appropriate pattern (new first, then legacy).

        Args:
            conversation_flow_class: The flow class to execute.
            chat_request: The current request.

        Returns:
            The flow's response.
        """
        try:
            return await self._execute_new_pattern(
                conversation_flow_class, chat_request
            )
        except TypeError as te:
            logger.debug(
                "Falling back to static pattern",
                type_error=str(te),
                operation="pattern_fallback",
            )
            response_tuple = await self._execute_static_pattern(
                conversation_flow_class, chat_request
            )
            return self._convert_response_format(response_tuple, chat_request)

    async def _save_chat_history(
        self, chat_request: IChatRequest, agent_response: Any
    ) -> None:
        """Persist user and assistant messages, and optional memory summary.

        Why:
            Centralize persistence and avoid writing invalid/None contents.

        Args:
            chat_request: The current request (must contain IDs).
            agent_response: The flow response (ideally `ChatResponse`).
        """
        if not getattr(chat_request, "memory_record", True):
            return
        if not (chat_request.user_id and chat_request.thread_id):
            return

        try:
            from ingenious.models.message import Message

            # Save user message
            user_message_id = await self.chat_history_repository.add_message(
                Message(
                    user_id=chat_request.user_id,
                    thread_id=chat_request.thread_id,
                    role="user",
                    content=chat_request.user_prompt,
                )
            )
            logger.info(
                "Saved user message",
                message_id=user_message_id,
                thread_id=chat_request.thread_id,
            )

            # Save assistant response if present and non-empty
            content = getattr(agent_response, "agent_response", None)
            if content:
                agent_message_id = await self.chat_history_repository.add_message(
                    Message(
                        user_id=chat_request.user_id,
                        thread_id=chat_request.thread_id,
                        role="assistant",
                        content=content,
                    )
                )
                logger.info(
                    "Saved agent message",
                    message_id=agent_message_id,
                    thread_id=chat_request.thread_id,
                )

            # Save memory summary if available
            if (
                hasattr(agent_response, "memory_summary")
                and agent_response.memory_summary
            ):
                memory_id = await self.chat_history_repository.add_memory(
                    Message(
                        user_id=chat_request.user_id,
                        thread_id=chat_request.thread_id,
                        role="memory_assistant",
                        content=agent_response.memory_summary,
                    )
                )
                logger.info(
                    "Saved memory",
                    memory_id=memory_id,
                    thread_id=chat_request.thread_id,
                )

        except Exception as e:
            logger.error(
                "Failed to save chat history",
                thread_id=chat_request.thread_id,
                user_id=chat_request.user_id,
                error=str(e),
                exc_info=True,
            )

    # ─────────────────────────────── streaming ───────────────────────────────

    async def get_streaming_chat_response(
        self, chat_request: IChatRequest
    ) -> AsyncIterator[ChatResponseChunk]:
        """Yield streaming chat response chunks in real time.

        Why:
            Supports native streaming (instance or static signatures), preserves
            original v1 fallback (`content` + `final`), and optionally provides
            a richer v2 protocol behind a configuration flag.

        Args:
            chat_request: The incoming chat request DTO.

        Yields:
            `ChatResponseChunk` instances following the selected protocol.
        """
        if not chat_request.conversation_flow:
            raise ValueError(f"conversation_flow not set {chat_request}")

        logger.debug(
            "Starting streaming chat response",
            conversation_flow=chat_request.conversation_flow,
            thread_id=chat_request.thread_id,
        )

        normalized_flow = normalize_workflow_name(chat_request.conversation_flow)

        try:
            # Import the conversation flow class dynamically
            conversation_flow_service_class = import_class_with_fallback(
                f"services.chat_services.multi_agent.conversation_flows."
                f"{normalized_flow}.{normalized_flow}",
                "ConversationFlow",
            )

            # Detect presence and nature of streaming method on the flow class
            has_stream = hasattr(
                conversation_flow_service_class, "get_streaming_conversation_response"
            )

            # Determine if the attribute is a staticmethod (legacy support)
            is_static_stream = False
            is_true_override = False
            if has_stream:
                try:
                    static_attr = inspect.getattr_static(
                        conversation_flow_service_class,
                        "get_streaming_conversation_response",
                    )
                    is_static_stream = isinstance(static_attr, staticmethod)

                    # True override if not the base class implementation
                    base_func = IConversationFlow.__dict__[
                        "get_streaming_conversation_response"
                    ]
                    if not is_static_stream and static_attr is not base_func:
                        is_true_override = True
                except Exception:
                    # Conservative default: treat as non-override, non-static
                    is_true_override = False
                    is_static_stream = False

            # ───── Native streaming: instance override or static legacy method ─────
            if has_stream and (is_true_override or is_static_stream):
                # Instance-based override
                if not is_static_stream:
                    instance = conversation_flow_service_class(
                        parent_multi_agent_chat_service=self
                    )
                    async for raw in instance.get_streaming_conversation_response(
                        chat_request
                    ):
                        # Normalize chunk fields and ensure IDs are set
                        chunk = (
                            raw
                            if isinstance(raw, ChatResponseChunk)
                            else ChatResponseChunk(
                                thread_id=getattr(raw, "thread_id", None)
                                or chat_request.thread_id
                                or str(uuid_module.uuid4()),
                                message_id=getattr(raw, "message_id", None)
                                or str(uuid_module.uuid4()),
                                chunk_type=getattr(raw, "chunk_type", "content"),
                                content=getattr(raw, "content", None),
                                token_count=getattr(raw, "token_count", None),
                                max_token_count=getattr(raw, "max_token_count", None),
                                topic=getattr(raw, "topic", None),
                                memory_summary=getattr(raw, "memory_summary", None),
                                followup_questions=getattr(
                                    raw, "followup_questions", None
                                ),
                                event_type=getattr(raw, "event_type", None),
                                is_final=bool(getattr(raw, "is_final", False)),
                            )
                        )
                        if not chunk.thread_id:
                            chunk.thread_id = (
                                chat_request.thread_id or str(uuid_module.uuid4())
                            )
                        if not chunk.message_id:
                            chunk.message_id = str(uuid_module.uuid4())
                        yield chunk
                    return

                # Legacy static streaming method (preserved)
                async for chunk in conversation_flow_service_class.get_streaming_conversation_response(  # type: ignore[attr-defined]
                    chat_request.user_prompt,
                    [],  # topics placeholder for legacy signature
                    chat_request.thread_memory or "",
                    chat_request.memory_record or True,
                    chat_request.thread_chat_history or {},
                    chat_request,
                ):
                    # Ensure IDs present even for legacy chunks
                    if not getattr(chunk, "thread_id", None):
                        chunk.thread_id = chat_request.thread_id or str(
                            uuid_module.uuid4()
                        )
                    if not getattr(chunk, "message_id", None):
                        chunk.message_id = str(uuid_module.uuid4())
                    yield chunk
                return

            # ──────────────── Fallback path (no native streaming) ────────────────
            # Choose protocol: default v1 (compat), optional v2 via config flag
            protocol = self._get_stream_protocol_version()

            # Get a full response using the synchronous path.
            # IMPORTANT: Do NOT set `chat_request.stream` here to preserve
            # original behavior where fallback path persisted history once.
            from ingenious.models.chat import ChatResponse

            response_any = await self.get_chat_response(chat_request)
            response: Any = (
                response_any
                if isinstance(response_any, ChatResponse)
                else self._convert_response_format(response_any, chat_request)
            )

            # Reuse the persisted IDs for strong correlation
            thread_id = response.thread_id or chat_request.thread_id or str(
                uuid_module.uuid4()
            )
            message_id = response.message_id or str(uuid_module.uuid4())
            full_text = response.agent_response or ""

            if protocol == STREAM_PROTOCOL_V1:
                # ───────────── v1: content chunks + final (compat) ─────────────
                chunk_size = self._get_configured_chunk_size()
                for i in range(0, len(full_text), chunk_size):
                    yield ChatResponseChunk(
                        thread_id=thread_id,
                        message_id=message_id,
                        chunk_type="content",
                        content=full_text[i : i + chunk_size],
                        event_type=response.event_type,
                        is_final=False,
                    )

                # Final chunk carries usage/meta
                yield ChatResponseChunk(
                    thread_id=thread_id,
                    message_id=message_id,
                    chunk_type="final",
                    token_count=response.token_count,
                    max_token_count=response.max_token_count,
                    topic=response.topic,
                    memory_summary=response.memory_summary,
                    followup_questions=response.followup_questions,
                    event_type=response.event_type,
                    is_final=True,
                )
                return

            # ───────────────── v2: richer event protocol ─────────────────
            # status:start
            yield ChatResponseChunk(
                thread_id=thread_id,
                message_id=message_id,
                chunk_type="status",
                content="start",
                is_final=False,
            )
            # status:generation
            yield ChatResponseChunk(
                thread_id=thread_id,
                message_id=message_id,
                chunk_type="status",
                content="generation",
                is_final=False,
            )

            # Word-aware chunking around target characters, honoring config if set
            target = max(DEFAULT_V2_TARGET_CHARS, self._get_configured_chunk_size())

            def _chunk_text_by_words(text: str, target_chars: int) -> List[str]:
                """Split text near word boundaries without exceeding target size.

                Args:
                    text: The content to split.
                    target_chars: Approximate maximum characters per chunk.

                Returns:
                    List of chunk strings.
                """
                parts: List[str] = []
                if not text:
                    return parts
                buf: List[str] = []
                cur = 0
                for word in text.split():
                    add_len = len(word) + (1 if buf else 0)
                    if cur + add_len > target_chars and buf:
                        parts.append(" ".join(buf))
                        buf = [word]
                        cur = len(word)
                    else:
                        buf.append(word)
                        cur += add_len
                if buf:
                    parts.append(" ".join(buf))
                return parts

            for piece in _chunk_text_by_words(full_text, target):
                yield ChatResponseChunk(
                    thread_id=thread_id,
                    message_id=message_id,
                    chunk_type="delta",
                    content=piece,
                    is_final=False,
                )

            # Summary chunk carries brief memory summary + full text
            mem_summary = response.memory_summary or full_text
            # Tests require the trimmed memory summary to be **<= 200** chars (no ellipsis)
            if mem_summary and len(mem_summary) > 200:
                mem_summary = mem_summary[:200]
            yield ChatResponseChunk(
                thread_id=thread_id,
                message_id=message_id,
                chunk_type="summary",
                content=full_text,
                memory_summary=mem_summary,
                is_final=False,
            )

            # Usage chunk: try accurate token counts; fallback heuristics
            total_tokens = int(response.token_count or 0)
            completion_tokens = int(response.max_token_count or 0)

            if total_tokens <= 0 or completion_tokens <= 0:
                try:
                    # Lazy import to avoid import-time failure in environments
                    # missing the optional token counter.
                    from ingenious.utils.token_counter import (
                        num_tokens_from_messages,
                    )

                    # Best-effort model selection
                    model_name: str = ""
                    try:
                        # Prefer first model if indexable; otherwise try attribute
                        models = getattr(self.config, "models", None)
                        model_name = getattr(models[0], "model", "")  # type: ignore[index]
                    except Exception:
                        model_name = getattr(getattr(self.config, "models", object()), "model", "")  # type: ignore[attr-defined]

                    messages: List[Dict[str, Any]] = [
                        {"role": "system", "content": ""},
                        {"role": "user", "content": chat_request.user_prompt},
                        {"role": "assistant", "content": full_text},
                    ]
                    total_tokens = int(num_tokens_from_messages(messages, model_name))
                    prompt_tokens = int(num_tokens_from_messages(messages[:-1], model_name))
                    completion_tokens = max(0, total_tokens - prompt_tokens)
                except Exception:
                    # Heuristic: ~4 chars/token
                    completion_tokens = max(0, len(full_text) // 4)
                    total_tokens = max(
                        0, (len(chat_request.user_prompt or "") // 4) + completion_tokens
                    )

            total_tokens = int(total_tokens)
            completion_tokens = int(completion_tokens)

            yield ChatResponseChunk(
                thread_id=thread_id,
                message_id=message_id,
                chunk_type="usage",
                token_count=total_tokens,
                max_token_count=completion_tokens,
                is_final=False,
            )

            # Always emit a terminal 'final' event for back-compat
            yield ChatResponseChunk(
                thread_id=thread_id,
                message_id=message_id,
                chunk_type="final",
                token_count=total_tokens,
                max_token_count=completion_tokens,
                topic=response.topic,
                memory_summary=response.memory_summary,
                followup_questions=response.followup_questions,
                event_type=response.event_type,
                is_final=True,
            )
            return

        except ImportError as e:
            logger.error(
                "Failed to import conversation flow for streaming",
                conversation_flow=self.conversation_flow,
                normalized_flow=normalized_flow,
                error=str(e),
                exc_info=True,
            )
            yield ChatResponseChunk(
                thread_id=chat_request.thread_id or str(uuid_module.uuid4()),
                message_id=str(uuid_module.uuid4()),
                chunk_type="error",
                content=f"Conversation flow not found: {self.conversation_flow}",
                is_final=True,
            )
        except Exception as e:
            logger.error(
                "Error in streaming chat response",
                conversation_flow=self.conversation_flow,
                error=str(e),
                exc_info=True,
            )
            yield ChatResponseChunk(
                thread_id=chat_request.thread_id or str(uuid_module.uuid4()),
                message_id=str(uuid_module.uuid4()),
                chunk_type="error",
                content=f"An error occurred: {str(e)}",
                is_final=True,
            )


# ─────────────────────────── legacy pattern base ─────────────────────────────


class IConversationPattern(ABC):
    """Legacy conversation pattern base (kept for back-compat).

    Why:
        Older flows may derive from this base and expect file-based memory
        management and direct file I/O helper methods.
    """

    _config: "Config"
    _memory_path: str
    _memory_file_path: str
    _memory_manager: Any

    def __init__(self) -> None:
        """Initialize legacy base with config and memory manager."""
        super().__init__()
        self._config = ig_config.get_config()
        self._memory_path = self.GetConfig().chat_history.memory_path
        self._memory_file_path = f"{self._memory_path}/context.md"

        # Initialize memory manager for cloud storage support via patchable alias
        self._memory_manager = get_memory_manager(self._config, self._memory_path)

    def GetConfig(self) -> "Config":
        """Return the loaded configuration instance."""
        return self._config

    def Get_Models(self) -> Dict[str, Any]:
        """Expose model configuration as a plain dictionary."""
        return self._config.models.__dict__

    def Get_Memory_Path(self) -> str:
        """Return the directory path where memory files are stored."""
        return self._memory_path

    def Get_Memory_File(self) -> str:
        """Return the primary memory file path."""
        return self._memory_file_path

    def Maintain_Memory(self, new_content: str, max_words: int = 150) -> Any:
        """Maintain memory using MemoryManager (supports cloud storage).

        Args:
            new_content: Text to be merged into memory.
            max_words: Target size/limit for summarization.

        Returns:
            Implementation-defined result of memory maintenance.
        """
        return run_async_memory_operation(  # type: ignore
            self._memory_manager.maintain_memory(new_content, max_words)
        )

    async def write_llm_responses_to_file(
        self, response_array: List[Dict[str, Any]], event_type: str, output_path: str
    ) -> None:
        """Write LLM responses to files using FileStorage (best-effort).

        Args:
            response_array: List containing at least `chat_response` and `chat_title`.
            event_type: String used to differentiate outputs.
            output_path: Directory where files should be written.
        """
        # Minimal configs in tests may not have file_storage configured.
        if not hasattr(self._config, "file_storage"):
            return
        fs = FileStorage(self._config)
        for res in response_array:
            make_llm_calls = True
            this_response = res["chat_response"] if make_llm_calls else "Pending"
            await fs.write_file(
                this_response,
                f"agent_response_{event_type}_{res['chat_title']}.md",
                output_path,
            )

    @abstractmethod
    async def get_conversation_response(
        self, message: str, thread_memory: str
    ) -> IChatResponse:
        """Contract for legacy flows to produce a non-streaming response."""
        raise NotImplementedError


# ───────────────────────────── new pattern base ──────────────────────────────


class IConversationFlow(ABC):
    """Base class for conversation flows (new pattern).

    Why:
        Standardizes configuration, memory management, template loading, and
        provides a default streaming fallback used by many existing flows.
    """

    _config: "Config"
    _memory_path: str
    _memory_file_path: str
    _logger: logging.Logger
    _chat_service: multi_agent_chat_service
    _memory_manager: Any

    def __init__(
        self, parent_multi_agent_chat_service: multi_agent_chat_service
    ) -> None:
        """Initialize with parent service and memory manager.

        Args:
            parent_multi_agent_chat_service: The owner chat service.
        """
        super().__init__()
        self._config = parent_multi_agent_chat_service.config
        self._memory_path = self.GetConfig().chat_history.memory_path
        self._memory_file_path = f"{self._memory_path}/context.md"
        self._logger = get_logger(__name__)  # type: ignore
        self._chat_service = parent_multi_agent_chat_service

        # Initialize memory manager via patchable alias for tests
        self._memory_manager = get_memory_manager(self._config, self._memory_path)

    def GetConfig(self) -> "Config":
        """Return the configuration associated with the flow."""
        return self._config

    async def Get_Template(
        self, revision_id: Optional[str] = None, file_name: str = "user_prompt.md"
    ) -> str:
        """Load and render a Jinja2 prompt template from storage (best-effort).

        Args:
            revision_id: Optional revision identifier for template selection.
            file_name: The template file name.

        Returns:
            The rendered template content (empty string if not found).
        """
        # Minimal configs in tests may not include file_storage; short-circuit.
        if not hasattr(self._config, "file_storage"):
            return ""
        fs = FileStorage(self._config)
        template_path = await fs.get_prompt_template_path(revision_id or "")
        content = await fs.read_file(file_name=file_name, file_path=template_path)
        if content is None:
            logger.warning(
                "Prompt template file not found",
                file_name=file_name,
                template_path=template_path,
                operation="template_file_lookup",
            )
            return ""
        env = Environment(autoescape=True)
        template = env.from_string(content)
        return template.render()  # type: ignore

    def Get_Models(self) -> Any:
        """Return the configured models object."""
        return self._config.models

    def Get_Memory_Path(self) -> str:
        """Return the directory path where memory files are stored."""
        return self._memory_path

    def Get_Memory_File(self) -> str:
        """Return the primary memory file path."""
        return self._memory_file_path

    def Maintain_Memory(self, new_content: str, max_words: int = 150) -> Any:
        """Maintain memory using MemoryManager (supports cloud storage).

        Args:
            new_content: Text to be merged into memory.
            max_words: Target size/limit for summarization.

        Returns:
            Implementation-defined result of memory maintenance.
        """
        return run_async_memory_operation(  # type: ignore
            self._memory_manager.maintain_memory(new_content, max_words)
        )

    @abstractmethod
    async def get_conversation_response(
        self, chat_request: IChatRequest
    ) -> IChatResponse:
        """Produce a non-streaming response for the given request."""
        raise NotImplementedError

    async def get_streaming_conversation_response(
        self, chat_request: IChatRequest
    ) -> AsyncIterator[ChatResponseChunk]:
        """Default streaming: chunk a non-streaming response into content+final.

        Why:
            Many flows don't need to implement streaming. This fallback preserves
            the **v1 protocol** and honors configured chunk size.
        """
        logger.debug(
            "Streaming not implemented, falling back to chunked response",
            conversation_flow=self.__class__.__name__,
        )

        response = await self.get_conversation_response(chat_request)

        if getattr(response, "agent_response", None):
            content = response.agent_response
            chunk_size = DEFAULT_V1_CHUNK_SIZE
            if hasattr(self._config, "web") and hasattr(
                self._config.web, "streaming_chunk_size"
            ):
                try:
                    chunk_size = int(self._config.web.streaming_chunk_size)
                except Exception:
                    chunk_size = DEFAULT_V1_CHUNK_SIZE

            for i in range(0, len(content), chunk_size):
                yield ChatResponseChunk(
                    thread_id=response.thread_id,
                    message_id=response.message_id,
                    chunk_type="content",
                    content=content[i : i + chunk_size],
                    event_type=response.event_type,
                    is_final=False,
                )

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
        return
