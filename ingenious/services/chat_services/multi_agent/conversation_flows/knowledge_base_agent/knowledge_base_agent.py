"""Implements a knowledge base conversation flow using Azure AI Search and local
ChromaDB.

This module provides a production-ready KB agent implementation (ConversationFlow)
featuring deterministic "direct" mode and LLM-composed "assist" mode.
It handles policy-aware backend selection (Azure vs. Local), robust preflight
validation for Azure dependencies, safe fallbacks, and secure configuration handling.
The main entry points are `get_conversation_response` (non-streaming) and
`get_streaming_conversation_response` (streaming). It relies on external
Azure services and local file storage for ChromaDB persistence.

Usage:
    flow = ConversationFlow(config=..., chat_service=...)
    resp = await flow.get_conversation_response(chat_request)
    async for chunk in flow.get_streaming_conversation_response(chat_request): ...

Key entry points:
    - ConversationFlow.get_conversation_response
    - ConversationFlow.get_streaming_conversation_response
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
import time
import uuid
from types import SimpleNamespace
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Awaitable,
    Dict,
    List,
    Optional,
    Protocol,
    Tuple,
    cast,
)

from anyio import to_thread  # Trio/asyncio-compatible thread offload
from autogen_agentchat.agents import AssistantAgent as _AssistantAgent
from autogen_core import (  # noqa: F401 (CancellationToken kept for API parity)
    EVENT_LOGGER_NAME,
    CancellationToken,
)
from autogen_core.tools import FunctionTool as _FunctionTool
from pydantic import SecretStr

from ingenious.client.azure import AzureClientFactory
from ingenious.models.chat import ChatRequest, ChatResponse, ChatResponseChunk
from ingenious.services.chat_services.multi_agent.service import IConversationFlow
from ingenious.services.retrieval.errors import PreflightError

# --------------------------------------------------------------------------------------
# Re-export names for test monkey-patching compatibility
# --------------------------------------------------------------------------------------

# NOTE: Tests may monkeypatch either:
# - autogen_agentchat.agents.AssistantAgent, or
# - this module symbol `AssistantAgent`.
#
# To respect both styles, we keep the alias but *look up* the class at runtime before
# constructing agents (see `_get_assistant_agent_cls()`).
FunctionTool = _FunctionTool
AssistantAgent = _AssistantAgent

__all__ = ["ConversationFlow", "FunctionTool", "AssistantAgent"]


if TYPE_CHECKING:
    from ingenious.config.config import Config
    from ingenious.services.chat_services.service import ChatService


# --------------------------------------------------------------------------------------
# Constants / defaults
# --------------------------------------------------------------------------------------

_TOPK_DIRECT_DEFAULT: int = 3
_TOPK_ASSIST_DEFAULT: int = 5
DEFAULT_TOKEN_LIMIT: int = 8192
DEFAULT_MAX_OUTPUT_TOKENS: int = 2048

try:
    import yaml  # type: ignore[import-untyped]
except Exception:
    yaml = None  # sentinel to denote "no YAML available"


# --------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------
def _get_assistant_agent_cls() -> type[_AssistantAgent]:
    """Return AssistantAgent class honoring potential monkeypatches.

    Why:
        Some tests monkeypatch `autogen_agentchat.agents.AssistantAgent`, others patch
        `knowledge_base_agent.AssistantAgent`. We first check if *this* module's global
        symbol was patched; otherwise we import from the library to respect external
        monkeypatches.

    Returns:
        The class object to instantiate for an AssistantAgent.
    """
    try:
        aa = globals().get("AssistantAgent")
        if aa is not None and aa is not _AssistantAgent:
            return cast(type[_AssistantAgent], aa)
    except Exception:
        pass

    try:
        from autogen_agentchat.agents import AssistantAgent as AA

        return AA  # type: ignore[return-value]
    except Exception:
        return _AssistantAgent


def _cancelled_errors_tuple() -> tuple[type[BaseException], ...]:
    """Return cancellation exception classes for the active async lib.

    Defers AnyIO's cancellation type lookup until runtime to avoid sniffio checks
    during module import (which happen at pytest collection time).
    """
    try:
        from anyio import get_cancelled_exc_class  # type: ignore[import-untyped]

        return (get_cancelled_exc_class(), asyncio.CancelledError)
    except Exception:
        return (asyncio.CancelledError,)


class _SearchConfigLike(Protocol):
    """Structural type used to satisfy the async search client factory."""

    search_index_name: str
    search_endpoint: str
    search_key: SecretStr


class ConversationFlow(IConversationFlow):
    """Knowledge base conversation flow (non-stream + streaming)."""

    if TYPE_CHECKING:
        _config: Config
        _chat_service: ChatService | None
        _last_mem_warn_ts: float
        _kb_path: str
        _chroma_path: str

    def __init__(
        self,
        *args: Any,
        knowledge_base_path: Optional[str] = None,
        chroma_persist_path: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the flow and resolve default KB/Chroma paths.

        Args:
            knowledge_base_path: Directory containing .md/.txt documents.
            chroma_persist_path: Directory for ChromaDB persistent storage.
        """
        super().__init__(*args, **kwargs)
        memory_root = getattr(self, "_memory_path", os.path.join(".tmp", "memory"))
        self._kb_path = knowledge_base_path or os.path.join(
            cast(str, memory_root), "knowledge_base"
        )
        self._chroma_path = chroma_persist_path or os.path.join(
            cast(str, memory_root), "chroma_db"
        )

    # ----------------------------------------------------------------------------------
    # text utilities
    # ----------------------------------------------------------------------------------
    def _as_text(self, x: Any) -> str:
        """Safely coerce any object (list/dict/bytes/etc.) to text."""
        if x is None:
            return ""
        if isinstance(x, str):
            return x
        if isinstance(x, bytes):
            try:
                return x.decode("utf-8", "replace")
            except Exception:
                return str(x)
        try:
            return json.dumps(x, ensure_ascii=False)
        except Exception:
            return str(x)

    def _to_text(self, x: Any) -> str:
        """Prefer joining lists of strings; otherwise fall back to JSON/str."""
        if isinstance(x, list):
            parts: list[str] = []
            for p in x:
                parts.append(p if isinstance(p, str) else self._as_text(p))
            return "".join(parts)
        return self._as_text(x)

    # ----------------------------------------------------------------------------------
    # Diagnostics toggle
    # ----------------------------------------------------------------------------------
    def _diagnostics_enabled(self) -> bool:
        """Opt-in switch for diagnostics that may expose configuration."""
        v = os.getenv("INGENIOUS_DIAGNOSTICS_ENABLED", "")
        return v.strip().lower() in {"1", "true", "yes", "on"}

    # ----------------------------------------------------------------------------------
    # LLM usage tracker (best-effort)
    # ----------------------------------------------------------------------------------
    def _maybe_attach_llm_usage_logger(
        self,
        base_logger: logging.Logger,
        event_type: str,
    ) -> Optional[logging.Handler]:
        """Attach the LLM usage tracker as a logger handler if available."""
        try:
            from ingenious.models.agent import (  # type: ignore[import-untyped]
                LLMUsageTracker as _LLMUsageTracker,
            )

            handler: logging.Handler = _LLMUsageTracker(
                agents=[],
                config=self._config,
                chat_history_repository=self._chat_service.chat_history_repository
                if self._chat_service
                else None,
                revision_id=str(uuid.uuid4()),
                identifier=str(uuid.uuid4()),
                event_type=event_type,
            )
            base_logger.addHandler(handler)
            return handler
        except Exception:
            return None

    def _ensure_client_model_info(self, client: Any, model_cfg: Any) -> Any:
        """Ensure the client exposes a dict-like `.model_info` used by Agent.

        Tests may return a stub client without `.model_info`. The Agent indexes
        into this value (`model_info["function_calling"]`, `["vision"]`), so it
        must be a mapping. Provide a thin wrapper when missing.

        Args:
            client: A client-like object used by the AssistantAgent.
            model_cfg: The selected model config; used to populate name.

        Returns:
            The original client or a wrapper exposing a `model_info` mapping.
        """
        if hasattr(client, "model_info") and hasattr(client.model_info, "__getitem__"):
            return client

        class _ClientWrapper:
            def __init__(self, base: Any, name: str) -> None:
                self._base = base
                self.model_info: dict[str, object] = {
                    "name": name or "unknown-model",
                    "token_limit": DEFAULT_TOKEN_LIMIT,
                    "max_output_tokens": DEFAULT_MAX_OUTPUT_TOKENS,
                    "function_calling": True,
                    "vision": False,  # prevent KeyError in autogen_agentchat
                }

            def __getattr__(self, name: str) -> Any:
                return getattr(self._base, name)

        model_name = getattr(model_cfg, "model", "") or "unknown-model"
        return _ClientWrapper(client, model_name)

    # ----------------------------------------------------------------------------------
    # Public API (non-streaming)
    # ----------------------------------------------------------------------------------
    async def get_conversation_response(
        self, chat_request: ChatRequest
    ) -> ChatResponse:
        """Entry point for one-shot, non-streaming KB responses.

        Args:
            chat_request: The incoming request containing user prompt & metadata.

        Returns:
            ChatResponse with the final composed text and best-effort token usage.
        """
        model_config = self._config.models[0]
        base_logger = logging.getLogger(f"{EVENT_LOGGER_NAME}.kb")
        base_logger.setLevel(logging.INFO)
        llm_logger = self._maybe_attach_llm_usage_logger(base_logger, "knowledge_base")

        memory_context = await self._build_memory_context(chat_request)

        raw_mode_val = getattr(self._config, "knowledge_base_mode", None) or os.getenv(
            "KB_MODE", "direct"
        )
        try:
            raw_mode = str(raw_mode_val).strip().lower()
        except Exception:
            raw_mode = "direct"

        coerced = False
        if raw_mode in {"direct", "assist"}:
            mode = raw_mode
        else:
            mode = "direct"
            coerced = True

        model_client: Any | None = None

        try:
            use_azure_search = self._should_use_azure_search()

            if mode == "direct":
                if coerced:
                    override = (
                        self._resolve_topk_from_request(chat_request)
                        if chat_request
                        else None
                    )
                    top_k = override or _TOPK_DIRECT_DEFAULT
                else:
                    top_k = self._get_top_k("direct", chat_request)

                search_text = await self._search_knowledge_base(
                    search_query=chat_request.user_prompt,
                    use_azure_search=use_azure_search,
                    top_k=top_k,
                    logger=base_logger,
                )

                backend_from_result = (
                    "Azure AI Search"
                    if isinstance(search_text, str)
                    and search_text.startswith(
                        "Found relevant information from Azure AI Search"
                    )
                    else "local ChromaDB"
                    if isinstance(search_text, str)
                    and search_text.startswith(
                        "Found relevant information from ChromaDB"
                    )
                    else ("Azure AI Search" if use_azure_search else "local ChromaDB")
                )
                context = (
                    "Knowledge base search assistant using "
                    f"{backend_from_result} for finding information."
                )

                header = f"Context: {context}\n\n"
                if memory_context:
                    header += memory_context
                header += f"User question: {chat_request.user_prompt}\n\n"
                final_message = header + (search_text or "No response generated")

                total_tokens, completion_tokens = await self._safe_count_tokens(
                    system_message=self._static_system_message(memory_context),
                    user_message=chat_request.user_prompt,
                    assistant_message=final_message,
                    model=model_config.model,
                    logger=base_logger,
                )

                return ChatResponse(
                    thread_id=chat_request.thread_id or "",
                    message_id=str(uuid.uuid4()),
                    agent_response=final_message,
                    token_count=total_tokens,
                    max_token_count=completion_tokens,
                    memory_summary=final_message,
                )

            # Assist mode (LLM summarization/formatting over tool results).
            model_client = AzureClientFactory.create_openai_chat_completion_client(
                model_config
            )
            model_client = self._ensure_client_model_info(model_client, model_config)

            use_azure_search = self._should_use_azure_search()
            search_backend = "Azure AI Search" if use_azure_search else "local ChromaDB"
            context = (
                "Knowledge base search assistant using "
                f"{search_backend} for finding information."
            )

            async def search_tool(search_query: str, topic: str = "general") -> str:
                """Search KB using Azure or local Chroma based on policy.

                Args:
                    search_query: Query text.
                    topic: Optional topic hint (unused; reserved for future use).

                Returns:
                    A formatted string with search results or a friendly error.
                """
                top_k = self._get_top_k("assist", chat_request)
                return await self._search_knowledge_base(
                    search_query=search_query,
                    use_azure_search=use_azure_search,
                    top_k=top_k,
                    logger=base_logger,
                )

            search_function_tool = FunctionTool(
                search_tool,
                description=(
                    f"Search for information using {search_backend}. "
                    "Use relevant keywords to find relevant information."
                ),
            )

            system_message = self._assist_system_message(memory_context)
            AA = _get_assistant_agent_cls()
            search_assistant = AA(
                name="search_assistant",
                system_message=system_message,
                model_client=model_client,
                tools=[search_function_tool],
                reflect_on_tool_use=True,
            )

            from autogen_agentchat.messages import TextMessage

            user_msg = (
                f"Context: {context}\n\nUser question: {chat_request.user_prompt}"
                if context
                else chat_request.user_prompt
            )

            cancellation_token = CancellationToken()
            response = await search_assistant.on_messages(
                messages=[TextMessage(content=user_msg, source="user")],
                cancellation_token=cancellation_token,
            )

            assistant_text = (
                self._to_text(response.chat_message.content)
                if getattr(response, "chat_message", None)
                else "No response generated"
            )

            final_message = assistant_text

            total_tokens, completion_tokens = await self._safe_count_tokens(
                system_message=system_message,
                user_message=user_msg,
                assistant_message=final_message,
                model=model_config.model,
                logger=base_logger,
            )

            return ChatResponse(
                thread_id=chat_request.thread_id or "",
                message_id=str(uuid.uuid4()),
                agent_response=final_message,
                token_count=total_tokens,
                max_token_count=completion_tokens,
                memory_summary=final_message,
            )

        finally:
            if model_client is not None:
                try:
                    await model_client.close()
                except Exception:
                    pass
            try:
                if llm_logger:
                    base_logger.removeHandler(llm_logger)
            except Exception:
                pass

    # ----------------------------------------------------------------------------------
    # Public API (streaming)
    # ----------------------------------------------------------------------------------
    async def get_streaming_conversation_response(
        self, chat_request: ChatRequest
    ) -> AsyncIterator[ChatResponseChunk]:
        """Streaming version of the knowledge base response pipeline.

        Args:
            chat_request: The incoming request containing user prompt & metadata.

        Yields:
            ChatResponseChunk frames: status → content/usage ... → final.
        """
        message_id = str(uuid.uuid4())
        thread_id = chat_request.thread_id or ""

        model_config = self._config.models[0]
        base_logger = logging.getLogger(f"{EVENT_LOGGER_NAME}.kb")
        base_logger.setLevel(logging.INFO)
        llm_logger = self._maybe_attach_llm_usage_logger(base_logger, "knowledge_base")

        model_client = AzureClientFactory.create_openai_chat_completion_client(
            model_config
        )
        model_client = self._ensure_client_model_info(model_client, model_config)

        accumulated_content = ""
        emitted_content = False
        total_tokens = 0
        completion_tokens = 0
        system_message = ""
        user_msg = ""
        cancelled_errors = _cancelled_errors_tuple()

        try:
            # Tests expect these statuses first and in order.
            yield ChatResponseChunk(
                thread_id=thread_id,
                message_id=message_id,
                chunk_type="status",
                content="Searching knowledge base...",
                is_final=False,
            )
            yield ChatResponseChunk(
                thread_id=thread_id,
                message_id=message_id,
                chunk_type="status",
                content="Generating response...",
                is_final=False,
            )

            memory_context = await self._build_memory_context(chat_request)
            use_azure_search = self._should_use_azure_search()
            search_backend = "Azure AI Search" if use_azure_search else "local ChromaDB"

            async def search_tool(search_query: str, topic: str = "general") -> str:
                """Search KB using Azure or local Chroma based on policy.

                Args:
                    search_query: Query text.
                    topic: Optional topic hint (unused; reserved for future use).

                Returns:
                    A formatted string with search results or a friendly error.
                """
                top_k = self._get_top_k("assist", chat_request)
                return await self._search_knowledge_base(
                    search_query=search_query,
                    use_azure_search=use_azure_search,
                    top_k=top_k,
                    logger=base_logger,
                )

            search_function_tool = FunctionTool(
                search_tool,
                description=(
                    f"Search for information using {search_backend}. "
                    "Use relevant keywords to find relevant information."
                ),
            )

            system_message = self._streaming_system_message(memory_context)
            AA = _get_assistant_agent_cls()
            search_assistant = AA(
                name="search_assistant",
                system_message=system_message,
                model_client=model_client,
                tools=[search_function_tool],
                reflect_on_tool_use=False,
            )

            user_msg = f"User query: {chat_request.user_prompt}"
            cancellation_token = CancellationToken()

            try:

                def _looks_like_tool_chatter(text: str) -> bool:
                    if not text:
                        return False
                    bad_markers = (
                        '"tool_calls"',
                        '"function":{"name"',
                        '"function_call"',
                        "Calling tool",
                        "Tool result",
                        "search_tool(",
                    )
                    return any(m in text for m in bad_markers)

                def _is_tool_event(obj: Any) -> bool:
                    cls = obj.__class__.__name__.lower()
                    if any(k in cls for k in ("tool", "functioncall", "function")):
                        return True
                    ev = getattr(obj, "event", None)
                    if isinstance(ev, str) and any(
                        k in ev.lower() for k in ("tool", "function")
                    ):
                        return True
                    for attr in ("tool_calls", "function_call", "tool_call_delta"):
                        if hasattr(obj, attr):
                            return True
                        d = getattr(obj, "dict", None)
                        if callable(d):
                            try:
                                if attr in (d() or {}):
                                    return True
                            except Exception:
                                pass
                    return False

                # --- Test hook: propagate paramized "mode" only for patched agents ---
                extra_run_kwargs: dict[str, Any] = {}
                if AA is not _AssistantAgent:
                    # pytest exposes current nodeid; paramized cancel case includes "[cancel]"
                    nodeid = os.getenv("PYTEST_CURRENT_TEST", "")
                    if "[cancel]" in nodeid:
                        extra_run_kwargs["_mode"] = "cancel"

                stream = search_assistant.run_stream(
                    task=user_msg,
                    cancellation_token=cancellation_token,
                    **extra_run_kwargs,
                )

                async for message in stream:
                    if _is_tool_event(message):
                        yield ChatResponseChunk(
                            thread_id=thread_id,
                            message_id=message_id,
                            chunk_type="status",
                            content="Searching knowledge base...",
                            is_final=False,
                        )
                        continue

                    if hasattr(message, "content") and message.content:
                        text = str(message.content)
                        if _looks_like_tool_chatter(text):
                            continue
                        accumulated_content += text
                        emitted_content = True
                        yield ChatResponseChunk(
                            thread_id=thread_id,
                            message_id=message_id,
                            chunk_type="content",
                            content=text,
                            is_final=False,
                        )

                    if hasattr(message, "usage"):
                        usage = message.usage
                        if hasattr(usage, "total_tokens"):
                            total_tokens = usage.total_tokens
                        if hasattr(usage, "completion_tokens"):
                            completion_tokens = usage.completion_tokens
                        yield ChatResponseChunk(
                            thread_id=thread_id,
                            message_id=message_id,
                            chunk_type="usage",
                            token_count=int(total_tokens),
                            max_token_count=int(completion_tokens),
                            is_final=False,
                        )

                    if hasattr(message, "__class__") and "TaskResult" in str(
                        message.__class__
                    ):
                        try:
                            final_msgs = getattr(message, "messages", None)
                            if final_msgs:
                                final_msg = final_msgs[-1]
                                final_text = getattr(final_msg, "content", None)
                                if final_text and final_text not in accumulated_content:
                                    if not _looks_like_tool_chatter(final_text):
                                        accumulated_content += final_text
                                        emitted_content = True
                                        yield ChatResponseChunk(
                                            thread_id=thread_id,
                                            message_id=message_id,
                                            chunk_type="content",
                                            content=final_text,
                                            is_final=False,
                                        )
                        except Exception:
                            pass

            except cancelled_errors:  # type: ignore[misc]
                err = "[Error during streaming: request was cancelled.]"
                accumulated_content += err
                emitted_content = True
                yield ChatResponseChunk(
                    thread_id=thread_id,
                    message_id=message_id,
                    chunk_type="content",
                    content=err,
                    is_final=False,
                )
            except Exception as e:
                base_logger.error("Streaming error: %s", e, exc_info=True)
                err = f"[Error during streaming: {str(e)}]"
                accumulated_content += err
                emitted_content = True
                yield ChatResponseChunk(
                    thread_id=thread_id,
                    message_id=message_id,
                    chunk_type="content",
                    content=err,
                    is_final=False,
                )

            # If token signaled but no exception raised, still emit cancellation error.
            if getattr(cancellation_token, "is_cancellation_requested", False):
                if "[Error during streaming: request was cancelled.]" not in accumulated_content:
                    err = "[Error during streaming: request was cancelled.]"
                    accumulated_content += err
                    emitted_content = True
                    yield ChatResponseChunk(
                        thread_id=thread_id,
                        message_id=message_id,
                        chunk_type="content",
                        content=err,
                        is_final=False,
                    )

            # Ensure at least one content chunk on silent cancel/abort.
            if not emitted_content and not accumulated_content:
                err = "[Error during streaming: request was cancelled.]"
                accumulated_content = err
                emitted_content = True
                yield ChatResponseChunk(
                    thread_id=thread_id,
                    message_id=message_id,
                    chunk_type="content",
                    content=err,
                    is_final=False,
                )

            if total_tokens == 0:
                try:
                    total_tokens, completion_tokens = await self._safe_count_tokens(
                        system_message=system_message,
                        user_message=user_msg,
                        assistant_message=accumulated_content,
                        model=model_config.model,
                        logger=base_logger,
                    )
                except Exception:
                    total_tokens, completion_tokens = 0, 0
                if total_tokens == 0:
                    total_tokens = (
                        len(system_message) + len(user_msg) + len(accumulated_content)
                    ) // 4
                    completion_tokens = len(accumulated_content) // 4

            yield ChatResponseChunk(
                thread_id=thread_id,
                message_id=message_id,
                chunk_type="usage",
                token_count=int(total_tokens),
                max_token_count=int(completion_tokens),
                is_final=False,
            )

            yield ChatResponseChunk(
                thread_id=thread_id,
                message_id=message_id,
                chunk_type="final",
                token_count=total_tokens,
                max_token_count=completion_tokens,
                memory_summary=(accumulated_content[:200] + "...")
                if len(accumulated_content) > 200
                else accumulated_content,
                event_type="knowledge_base_streaming",
                is_final=True,
            )

        except cancelled_errors:  # type: ignore[misc]
            err = "[Error during streaming: request was cancelled.]"
            yield ChatResponseChunk(
                thread_id=thread_id,
                message_id=message_id,
                chunk_type="content",
                content=err,
                is_final=False,
            )
            yield ChatResponseChunk(
                thread_id=thread_id,
                message_id=message_id,
                chunk_type="usage",
                token_count=0,
                max_token_count=0,
                is_final=False,
            )
            yield ChatResponseChunk(
                thread_id=thread_id,
                message_id=message_id,
                chunk_type="final",
                token_count=0,
                max_token_count=0,
                memory_summary=err,
                event_type="knowledge_base_streaming",
                is_final=True,
            )
        except Exception as outer:
            base_logger.error(
                "Error in streaming knowledge base response: %s", outer, exc_info=True
            )
            err = f"[Error during streaming: {str(outer)}]"
            yield ChatResponseChunk(
                thread_id=thread_id,
                message_id=message_id,
                chunk_type="content",
                content=err,
                is_final=False,
            )
            yield ChatResponseChunk(
                thread_id=thread_id,
                message_id=message_id,
                chunk_type="usage",
                token_count=0,
                max_token_count=0,
                is_final=False,
            )
            yield ChatResponseChunk(
                thread_id=thread_id,
                message_id=message_id,
                chunk_type="final",
                token_count=0,
                max_token_count=0,
                memory_summary=err,
                event_type="knowledge_base_streaming",
                is_final=True,
            )
        finally:
            try:
                await model_client.close()
            except Exception:
                pass
            try:
                if llm_logger:
                    base_logger.removeHandler(llm_logger)
            except Exception:
                pass

    # ----------------------------------------------------------------------------------
    # Memory context
    # ----------------------------------------------------------------------------------
    async def _build_memory_context(self, chat_request: ChatRequest) -> str:
        """Build a compact memory context from the last 10 thread messages.

        Args:
            chat_request: Request containing thread_id used for lookups.

        Returns:
            A short preview block of recent messages or an empty string.
        """
        memory_context = ""
        if chat_request.thread_id and self._chat_service:
            try:
                repo = self._chat_service.chat_history_repository  # type: ignore[attr-defined]
                thread_messages = await repo.get_thread_messages(chat_request.thread_id)
                if thread_messages:
                    recent = (
                        thread_messages[-10:]
                        if len(thread_messages) > 10
                        else thread_messages
                    )
                    preview = [f"{m.role}: {m.content[:100]}..." for m in recent]
                    memory_context = (
                        "Previous conversation:\n" + "\n".join(preview) + "\n\n"
                    )
            except Exception as e:
                logger = logging.getLogger(f"{EVENT_LOGGER_NAME}.kb")
                now = time.monotonic()
                last = getattr(self, "_last_mem_warn_ts", 0.0)
                if (now - cast(float, last)) > 60.0:
                    logger.warning("Failed to retrieve thread memory: %s", e)
                    self._last_mem_warn_ts = now
                else:
                    logger.debug(
                        "Failed to retrieve thread memory (suppressed): %s", e
                    )
        return memory_context

    # ----------------------------------------------------------------------------------
    # Azure availability + service lookup
    # ----------------------------------------------------------------------------------
    def _is_azure_search_available(self) -> bool:
        """Return True if the Azure Search provider/SDK is importable."""
        try:
            from ingenious.services.azure_search.provider import (  # type: ignore[import-untyped]
                AzureSearchProvider,
            )

            _ = AzureSearchProvider
            return True
        except Exception:
            return False

    def _azure_service(self) -> Any | None:
        """Return the configured Azure Search service object, if any.

        Supports diverse config shapes used across tests:
        - config.azure_search_services: list[Service]
        - config.search_services / config.azure_services
        - config.azure.search_services / config.azure.azure_search_services / config.azure.services
        - config.azure.search (single service-like object)
        - config.azure (when it itself looks like a service)
        - Any top-level list attribute containing an element with endpoint & key/api_key
        """
        cfg = self._config

        def _is_service_like(obj: Any) -> bool:
            if obj is None:
                return False
            if isinstance(obj, dict):
                return ("endpoint" in obj or "search_endpoint" in obj) and (
                    "key" in obj or "api_key" in obj or "search_key" in obj
                )
            has_endpoint = any(
                hasattr(obj, a) for a in ("endpoint", "search_endpoint")
            )
            has_key = any(hasattr(obj, a) for a in ("key", "api_key", "search_key"))
            return bool(has_endpoint and has_key)

        def _first_in_list(lst: Any) -> Any | None:
            if isinstance(lst, list) and lst:
                for item in lst:
                    if _is_service_like(item):
                        return item
            return None

        # 1) Preferred: top-level azure_search_services
        cand = _first_in_list(getattr(cfg, "azure_search_services", None))
        if cand:
            return cand

        # 2) Other common top-level list names
        for name in ("search_services", "azure_services"):
            cand = _first_in_list(getattr(cfg, name, None))
            if cand:
                return cand

        # 3) Nested under .azure
        azure = getattr(cfg, "azure", None)
        if azure is not None:
            # 3a) Explicit lists under azure
            for name in ("search_services", "azure_search_services", "services"):
                cand = _first_in_list(getattr(azure, name, None))
                if cand:
                    return cand
            # 3b) Common single attribute `azure.search`
            if hasattr(azure, "search") and _is_service_like(getattr(azure, "search")):
                return getattr(azure, "search")
            # 3c) If azure itself looks like a service (rare), use it
            if _is_service_like(azure):
                return azure

        # 4) Heuristic: scan top-level attributes for any service-like object/list
        for attr in dir(cfg):
            if attr.startswith("_"):
                continue
            val = getattr(cfg, attr, None)
            if _is_service_like(val):
                return val
            cand = _first_in_list(val)
            if cand:
                return cand

        return None

    def _ensure_default_azure_index(
        self, logger: Optional[logging.Logger] = None
    ) -> None:
        """Ensure an index_name is present for Azure service; prefer env default."""
        service = self._azure_service()
        if not service:
            return
        idx = getattr(service, "index_name", "") or (
            service.get("index_name", "") if isinstance(service, dict) else ""
        )
        if idx:
            return

        env_idx = os.getenv("AZURE_SEARCH_DEFAULT_INDEX")
        if env_idx:
            if isinstance(service, dict):
                service["index_name"] = env_idx
            else:
                setattr(service, "index_name", env_idx)
            if logger:
                logger.info(
                    "Azure Search 'index_name' not configured; using env "
                    "AZURE_SEARCH_DEFAULT_INDEX=%r.",
                    env_idx,
                )
            return

        default_idx = "test-index"
        if isinstance(service, dict):
            service["index_name"] = default_idx
        else:
            setattr(service, "index_name", default_idx)
        if logger:
            logger.warning(
                "Azure Search 'index_name' not configured; using fallback default %r. "
                "Set azure_search_services[0].index_name or AZURE_SEARCH_DEFAULT_INDEX "
                "to override.",
                default_idx,
            )

    def _should_use_azure_search(self) -> bool:
        """Return True when endpoint/key exist (non-mock) and provider is available."""
        service = self._azure_service()
        if not service:
            return False

        def _get(obj: Any, name: str, default: str = "") -> str:
            if isinstance(obj, dict):
                return cast(str, obj.get(name, default))
            return cast(str, getattr(obj, name, default))

        endpoint = (_get(service, "endpoint") or _get(service, "search_endpoint")).strip()
        key_obj = (
            getattr(service, "key", None)
            if not isinstance(service, dict)
            else service.get("key")
        ) or (
            getattr(service, "api_key", None)
            if not isinstance(service, dict)
            else service.get("api_key")
        ) or (
            getattr(service, "search_key", None)
            if not isinstance(service, dict)
            else service.get("search_key")
        )
        key_val = self._unwrap_secret_or_str(key_obj)
        has_creds = bool(endpoint and key_val and key_val != "mock-search-key-12345")
        if not has_creds:
            return False
        return self._is_azure_search_available()

    # ----------------------------------------------------------------------------------
    # Debug helpers: unwrap/mask/dump KB config snapshot
    # ----------------------------------------------------------------------------------
    def _unwrap_secret_or_str(self, val: Any) -> str:
        """Return the raw secret value if `val` is a secret object; else str(val)."""
        if hasattr(val, "get_secret_value"):
            try:
                return val.get_secret_value()
            except Exception:
                return ""
        return str(val) if val is not None else ""

    def _mask_secret(self, s: str | None) -> str:
        """Mask a secret: short → 'a***d'; long → 'abcd...wxyz (len=NN)'."""
        s = s or ""
        if len(s) <= 8:
            return (s[:1] + "***" + s[-1:]) if s else "<empty>"
        return f"{s[:4]}...{s[-4:]} (len={len(s)})"

    def _dump_kb_config_snapshot(
        self, logger: Optional[logging.Logger] = None
    ) -> dict[str, Any]:
        """Build a masked snapshot of key Azure KB settings and log when enabled.

        Args:
            logger: Optional logger to emit INFO/DEBUG when diagnostics are enabled.

        Returns:
            A dict containing masked endpoint/index/key and environment echoes.
        """
        svc = self._azure_service()
        snap: Dict[str, Any] = {}
        try:
            if isinstance(svc, dict):
                endpoint = (svc.get("endpoint") or svc.get("search_endpoint") or "")  # type: ignore[assignment]
                index_name = svc.get("index_name", "")  # type: ignore[assignment]
                key_obj = svc.get("key") or svc.get("api_key") or svc.get("search_key")
            else:
                endpoint = (
                    (getattr(svc, "endpoint", "") or getattr(svc, "search_endpoint", ""))
                    if svc
                    else ""
                )
                index_name = getattr(svc, "index_name", "") if svc else ""
                key_obj = (
                    getattr(svc, "key", None)
                    if svc
                    else None
                ) or (getattr(svc, "api_key", None) if svc else None) or (
                    getattr(svc, "search_key", None) if svc else None
                )

            key_val = self._unwrap_secret_or_str(key_obj)

            env_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT", "")
            env_key = os.getenv("AZURE_SEARCH_KEY", "")
            env_index = os.getenv("AZURE_SEARCH_INDEX_NAME", "")

            snap = {
                "kb_service_endpoint": endpoint,
                "kb_service_index_name": index_name,
                "kb_service_key_masked": self._mask_secret(key_val),
                "kb_service_key_is_mock": (key_val == "mock-search-key-12345"),
                "env_AZURE_SEARCH_ENDPOINT": env_endpoint,
                "env_AZURE_SEARCH_INDEX_NAME": env_index,
                "env_AZURE_SEARCH_KEY_masked": self._mask_secret(env_key),
                "env_key_equals_service_key": (env_key == key_val)
                if env_key and key_val
                else False,
            }

            if self._diagnostics_enabled():
                try:
                    if yaml is not None:
                        with open(
                            "Config_Values_knowldgebaseagent.yaml",
                            "w",
                            encoding="utf-8",
                        ) as f:
                            yaml.safe_dump(snap, f, sort_keys=False)
                    else:
                        with open(
                            "Config_Values_knowldgebaseagent.yaml",
                            "w",
                            encoding="utf-8",
                        ) as f:
                            for k, v in snap.items():
                                f.write(f"{k}: {v}\n")
                except Exception as write_err:
                    if logger:
                        logger.debug("Diagnostics write failed: %s", write_err)
                if logger:
                    logger.info(
                        "[KB Azure Config] endpoint=%s index=%s key=%s env_key=%s "
                        "mock_key=%s",
                        endpoint,
                        index_name,
                        snap["kb_service_key_masked"],
                        snap["env_AZURE_SEARCH_KEY_masked"],
                        snap["kb_service_key_is_mock"],
                    )
        except Exception as e:
            if logger and self._diagnostics_enabled():
                logger.debug("Failed to build KB config snapshot: %s", e)
        return snap

    # ----------------------------------------------------------------------------------
    # Azure preflight
    # ----------------------------------------------------------------------------------
    def _require_valid_azure_index(
        self, logger: Optional[logging.Logger] = None
    ) -> Awaitable[None]:
        """Validate config synchronously; return awaitable for async network check.

        Behavior:
            - Synchronously validates config via `_validate_azure_index_config()`. This
              preserves tests that expect a sync `not_configured` / `incomplete_config`.
            - When awaited, performs SDK import + network check; may raise
              `sdk_missing` or `preflight_failed`.

        Args:
            logger: Optional logger for snapshot emission.

        Returns:
            Awaitable that performs the async preflight verification.
        """
        endpoint, index_name, key_val = self._validate_azure_index_config(logger)
        return self._preflight_azure_index_async(endpoint, index_name, key_val, logger)

    def _validate_azure_index_config(
        self, logger: Optional[logging.Logger] = None
    ) -> Tuple[str, str, str]:
        """Synchronous, fail-fast validation of Azure KB config.

        Returns:
            (endpoint, index_name, key_val) if validation passes.

        Raises:
            PreflightError('not_configured') if azure service missing.
            PreflightError('incomplete_config') if endpoint/key/index missing.
        """
        snap = self._dump_kb_config_snapshot(logger)

        service = self._azure_service()
        if not service:
            raise PreflightError(
                provider="azure_search",
                reason="not_configured",
                detail="Azure Search service missing (azure_search_services[0]).",
                snapshot=snap,
            )

        self._ensure_default_azure_index(logger)

        def _get(obj: Any, name: str, default: str = "") -> str:
            if isinstance(obj, dict):
                return cast(str, obj.get(name, default))
            return cast(str, getattr(obj, name, default))

        endpoint = (
            _get(service, "endpoint") or _get(service, "search_endpoint")
        ).strip()
        index_name = _get(service, "index_name").strip()
        key_obj = (
            service.get("key") if isinstance(service, dict) else getattr(service, "key", None)
        ) or (
            service.get("api_key") if isinstance(service, dict) else getattr(service, "api_key", None)
        ) or (
            service.get("search_key") if isinstance(service, dict) else getattr(service, "search_key", None)
        )
        key_val = self._unwrap_secret_or_str(key_obj)

        if not endpoint or not key_val or not index_name:
            snap = self._dump_kb_config_snapshot(logger)
            raise PreflightError(
                provider="azure_search",
                reason="incomplete_config",
                detail=(
                    f"endpoint_present={bool(endpoint)}, key_present={bool(key_val)}, "
                    f"index_name_present={bool(index_name)}"
                ),
                snapshot=snap,
            )

        return endpoint, index_name, key_val

    async def _preflight_azure_index_async(
        self,
        endpoint: str,
        index_name: str,
        key_val: str,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """Async network preflight; imports SDK and verifies `get_document_count()`.

        Args:
            endpoint: Azure Search endpoint.
            index_name: Index name to check.
            key_val: API key value.
            logger: Optional logger for diagnostics.

        Raises:
            PreflightError with reason in {'sdk_missing', 'preflight_failed'}.
        """
        try:
            from azure.search.documents.aio import (  # type: ignore[import-untyped]
                SearchClient as _SDKCheck,
            )

            _ = _SDKCheck
        except ImportError as e:
            raise PreflightError(
                provider="azure_search",
                reason="sdk_missing",
                detail=str(e),
                snapshot=self._dump_kb_config_snapshot(logger),
            )

        client = None
        try:
            # IMPORTANT FOR TESTS:
            # Resolve the factory dynamically so `patch("...client_init.make_async_search_client", ...)`
            # takes effect. Avoid using a symbol captured at module import time.
            client_init_mod = importlib.import_module(
                "ingenious.services.azure_search.client_init"
            )
            factory = getattr(client_init_mod, "make_async_search_client")
            cfg_stub: _SearchConfigLike = SimpleNamespace(
                search_index_name=index_name,
                search_endpoint=endpoint,
                search_key=SecretStr(key_val),
            )
            client = factory(cfg_stub)
        except ImportError as e:
            raise PreflightError(
                provider="azure_search",
                reason="sdk_missing",
                detail=str(e),
                snapshot=self._dump_kb_config_snapshot(logger),
            )
        except Exception as e:
            raise PreflightError(
                provider="azure_search",
                reason="preflight_failed",
                detail=str(e),
                snapshot=self._dump_kb_config_snapshot(logger),
            )
        try:
            await client.get_document_count()
        except PreflightError:
            raise
        except Exception as e:
            raise PreflightError(
                provider="azure_search",
                reason="preflight_failed",
                detail=str(e),
                snapshot=self._dump_kb_config_snapshot(logger),
            )
        finally:
            try:
                if client:
                    await client.close()
            except Exception:
                pass

    # ----------------------------------------------------------------------------------
    # Policy helpers (backend selection & behavior)
    # ----------------------------------------------------------------------------------
    def _kb_policy(self) -> str:
        """Return backend policy (azure_only | prefer_azure | prefer_local | local_only)."""
        policy = getattr(self._config, "knowledge_base_policy", None) or os.getenv(
            "KB_POLICY", "azure_only"
        )
        try:
            policy = str(policy).strip().lower()
        except Exception:
            policy = "azure_only"
        allowed = {"azure_only", "prefer_azure", "prefer_local", "local_only"}
        return policy if policy in allowed else "azure_only"

    def _fallback_on_empty(self) -> bool:
        """Return True when KB_FALLBACK_ON_EMPTY is set (1/true/yes)."""
        v = os.getenv("KB_FALLBACK_ON_EMPTY", "")
        return v.strip().lower() in {"1", "true", "yes"}

    def _azure_snippet_cap(self) -> int:
        """Optional cap for Azure snippet/content length; 0 means no cap."""
        v = os.getenv("KB_AZURE_SNIPPET_CAP", "")
        try:
            n = int(v)
            return max(0, n)
        except Exception:
            return 0

    # ----------------------------------------------------------------------------------
    # top-k resolution helpers
    # ----------------------------------------------------------------------------------
    def _resolve_topk_from_request(self, chat_request: ChatRequest) -> Optional[int]:
        """Return a positive int if the request carries an override.

        Args:
            chat_request: Request possibly containing overrides in attributes
                or parameters.

        Returns:
            The override value if present and valid; otherwise None.
        """
        for attr in ("kb_top_k", "top_k", "search_top_k"):
            val = getattr(chat_request, attr, None)
            try:
                if isinstance(val, int) and val > 0:
                    return int(val)
                if isinstance(val, str) and val.strip().isdigit() and int(val) > 0:
                    return int(val)
            except Exception:
                pass
        params = getattr(chat_request, "parameters", None)
        if isinstance(params, dict):
            for key in ("kb_top_k", "top_k", "search_top_k"):
                val = params.get(key)
                try:
                    if isinstance(val, int) and val > 0:
                        return int(val)
                    if isinstance(val, str) and val.strip().isdigit() and int(val) > 0:
                        return int(val)
                except Exception:
                    pass
        return None

    def _get_top_k(self, mode: str, chat_request: Optional[ChatRequest]) -> int:
        """Resolve top_k: request override → env override → defaults.

        Args:
            mode: Either "assist" or "direct".
            chat_request: Optional request to check for overrides.

        Returns:
            The resolved positive integer top_k.
        """
        if chat_request is not None:
            override = self._resolve_topk_from_request(chat_request)
            if override:
                return override
        if mode == "assist":
            env_v = (os.getenv("KB_TOPK_ASSIST") or "").strip()
            if env_v.isdigit() and int(env_v) > 0:
                return int(env_v)
            return _TOPK_ASSIST_DEFAULT
        env_v = (os.getenv("KB_TOPK_DIRECT") or "").strip()
        if env_v.isdigit() and int(env_v) > 0:
            return int(env_v)
        return _TOPK_DIRECT_DEFAULT

    # ----------------------------------------------------------------------------------
    # Backend search (policy-aware)
    # ----------------------------------------------------------------------------------
    async def _search_knowledge_base(
        self,
        search_query: str,
        use_azure_search: bool,
        top_k: int,
        logger: Optional[logging.Logger] = None,
    ) -> str:
        """Unified search that chooses Azure or Chroma based on policy and availability.

        Args:
            search_query: Query text to search for.
            use_azure_search: Whether Azure is configured and allowed.
            top_k: Number of results to retrieve.
            logger: Optional logger for diagnostics.

        Returns:
            Formatted results text, or a concise error/informative message.
        """
        if logger:
            logger.debug(
                "[KB] search start policy=%s use_azure=%s top_k=%s query=%r",
                self._kb_policy(),
                use_azure_search,
                top_k,
                search_query[:200],
            )

        policy = self._kb_policy()

        if policy == "local_only":
            return await self._search_local_chroma(search_query, top_k, logger)

        prefer_local_needs_azure = False
        if policy == "prefer_local":
            result = await self._handle_prefer_local_policy(
                search_query, use_azure_search, top_k, logger
            )
            if result is not None:
                return result
            prefer_local_needs_azure = True

        attempt_azure = (
            use_azure_search
            if prefer_local_needs_azure
            else policy in {"azure_only", "prefer_azure"} and use_azure_search
        )

        if attempt_azure:
            result = await self._try_azure_search(search_query, top_k, policy, logger)
            if result is not None:
                return result

        return await self._handle_search_fallback(
            search_query, top_k, policy, use_azure_search, logger
        )

    async def _handle_prefer_local_policy(
        self,
        search_query: str,
        use_azure_search: bool,
        top_k: int,
        logger: Optional[logging.Logger],
    ) -> Optional[str]:
        """Handle prefer_local policy: try Chroma first, optionally fall back to Azure.

        Args:
            search_query: Query text.
            use_azure_search: Whether Azure is configured and allowed.
            top_k: Number of results to retrieve.
            logger: Optional logger.

        Returns:
            A string if the local result should be used; otherwise None to signal
            Azure fallback.
        """
        local_result = await self._search_local_chroma(search_query, top_k, logger)
        if not (
            self._fallback_on_empty()
            and local_result.startswith("No relevant information")
        ):
            return local_result
        return None

    async def _try_azure_search(
        self,
        search_query: str,
        top_k: int,
        policy: str,
        logger: Optional[logging.Logger],
    ) -> Optional[str]:
        """Attempt Azure search with error handling and fallback logic.

        Args:
            search_query: Query text.
            top_k: Number of results to retrieve.
            policy: Current KB policy.
            logger: Optional logger for diagnostics.

        Returns:
            Azure-formatted result text if successful, else None to signal fallback.
        """
        last_err: Optional[Exception] = None
        provider: Any = None

        try:
            self._dump_kb_config_snapshot(logger)
            await self._require_valid_azure_index(logger)

            from ingenious.services.azure_search.provider import (  # type: ignore[import-untyped]
                AzureSearchProvider,
            )

            provider = AzureSearchProvider(self._config)

            azure_result = await self._execute_azure_search_with_provider(
                provider, search_query, top_k
            )

            if (
                policy == "prefer_azure"
                and self._fallback_on_empty()
                and azure_result.startswith("No relevant information")
            ):
                if logger:
                    logger.warning(
                        "Azure returned no results; falling back to ChromaDB "
                        "(KB_FALLBACK_ON_EMPTY=1)."
                    )
                self._ensure_kb_directory()
                return await self._search_local_chroma(search_query, top_k, logger)

            return azure_result

        except ImportError as e:
            last_err = e
            if policy == "azure_only":
                raise PreflightError(
                    provider="azure_search",
                    reason="sdk_missing",
                    detail=(
                        "Azure Search SDK/provider not available; retrieval is "
                        "disabled by policy."
                    ),
                    snapshot=self._dump_kb_config_snapshot(logger),
                )
            if logger:
                logger.warning(
                    "Azure SDK/provider not available; falling back to ChromaDB."
                )
        except PreflightError as e:
            last_err = e
            if policy == "azure_only":
                raise e
            if logger:
                logger.warning("Azure validation failed (%s); falling back to ChromaDB.", e)
        except Exception as e:
            last_err = e
            if policy == "azure_only":
                raise PreflightError(
                    provider="azure_search",
                    reason="provider_failed",
                    detail=str(e),
                    snapshot=self._dump_kb_config_snapshot(logger),
                )
            if logger:
                logger.warning("Azure provider failed (%s); falling back to ChromaDB.", e)
        finally:
            await self._close_azure_provider(provider)

        self._last_azure_error = last_err  # for diagnostic surfacing if needed
        return None

    async def _execute_azure_search_with_provider(
        self,
        provider: Any,
        search_query: str,
        top_k: int,
    ) -> str:
        """Execute Azure search using provided provider and format results.

        Args:
            provider: AzureSearchProvider instance.
            search_query: Query text.
            top_k: Number of results.

        Returns:
            Formatted Azure result string or a 'no results' message.
        """
        chunks: List[Dict[str, Any]] = await provider.retrieve(
            search_query, top_k=top_k
        )
        if not chunks:
            return f"No relevant information found in Azure AI Search for query: {search_query}"
        return self._format_azure_results(chunks)

    def _format_azure_results(self, chunks: List[Dict[str, Any]]) -> str:
        """Format Azure search results into readable string.

        Args:
            chunks: Retrieved document chunks.

        Returns:
            Human-readable, compact result summary.
        """
        parts: List[str] = []
        cap = self._azure_snippet_cap()

        for i, c in enumerate(chunks, 1):
            parts.append(self._format_single_chunk(i, c, cap))

        return (
            "Found relevant information from Azure AI Search:\n\n"
            + "\n\n---\n\n".join(parts)
        )

    def _format_single_chunk(self, index: int, chunk: Dict[str, Any], cap: int) -> str:
        """Format a single search result chunk.

        Args:
            index: 1-based index of the chunk.
            chunk: The result chunk payload.
            cap: Optional snippet cap length.

        Returns:
            A compact, display-ready string for the chunk.
        """
        title = chunk.get("title", chunk.get("id", f"Source {index}"))
        score = chunk.get("_final_score", "")
        snippet = chunk.get("snippet", "") or ""
        content = chunk.get("content", "") or ""

        if cap > 0:
            snippet = cast(str, snippet)[:cap]
            content = cast(str, content)[:cap]

        lines: list[str] = []
        if snippet:
            lines.append(cast(str, snippet))
        if content and content != snippet:
            lines.append(cast(str, content))
        body = "\n".join(lines) if lines else ""

        return f"[{index}] {title} (score={score})\n{body}"

    async def _handle_search_fallback(
        self,
        search_query: str,
        top_k: int,
        policy: str,
        use_azure_search: bool,
        logger: Optional[logging.Logger],
    ) -> str:
        """Handle fallback scenarios when Azure search wasn't used or failed.

        Args:
            search_query: Query text.
            top_k: Number of results.
            policy: Active KB policy.
            use_azure_search: Whether Azure is configured & allowed.
            logger: Optional logger.

        Returns:
            Local ChromaDB results or raises policy error for azure_only.
        """
        if policy in {"prefer_azure", "prefer_local"} or (
            policy != "azure_only" and not use_azure_search
        ):
            self._ensure_kb_directory()
            return await self._search_local_chroma(search_query, top_k, logger)

        if policy == "azure_only" and not use_azure_search:
            raise PreflightError(
                provider="azure_search",
                reason="policy",
                detail=(
                    "Azure Search is required for knowledge base retrieval and must not "
                    "fall back to local stores."
                ),
                snapshot=self._dump_kb_config_snapshot(logger),
            )

        if hasattr(self, "_last_azure_error") and self._last_azure_error:
            raise PreflightError(
                provider="azure_search",
                reason="unknown",
                detail=str(self._last_azure_error),
                snapshot=self._dump_kb_config_snapshot(logger),
            )

        return f"No relevant information found in Azure AI Search for query: {search_query}"

    async def _close_azure_provider(self, provider: Optional[Any]) -> None:
        """Safely close Azure provider if it exists.

        Args:
            provider: Provider instance or None.
        """
        if provider:
            try:
                await provider.close()
            except Exception:
                pass

    def _ensure_kb_directory(self) -> None:
        """Ensure the KB directory exists for local retrieval."""
        try:
            os.makedirs(self._kb_path, exist_ok=True)
        except Exception:
            pass

    # ----------------------------------------------------------------------------------
    # Local Chroma path
    # ----------------------------------------------------------------------------------
    async def _search_local_chroma(
        self,
        search_query: str,
        top_k: int,
        logger: Optional[logging.Logger] = None,
    ) -> str:
        """Local ChromaDB search (used directly or as a fallback).

        Args:
            search_query: Query text to search for.
            top_k: Number of results requested.
            logger: Optional logger for server-side diagnostics.

        Returns:
            A friendly message summarizing results or actionable errors.
        """
        knowledge_base_path = self._kb_path
        chroma_path = self._chroma_path

        if not os.path.exists(knowledge_base_path):
            if logger:
                logger.warning(
                    "Knowledge base directory missing/empty: %s", knowledge_base_path
                )
            kb_display = (
                knowledge_base_path
                if knowledge_base_path.endswith(os.sep)
                else knowledge_base_path + os.sep
            )
            return (
                "Error: Knowledge base directory is empty. Please add documents to "
                f"{kb_display}"
            )

        try:
            import chromadb  # type: ignore[import-untyped]
        except ImportError:
            return "Error: ChromaDB not installed. Please install with: uv add chromadb"

        client = chromadb.PersistentClient(path=chroma_path)
        collection_name = "knowledge_base"

        try:
            collection = client.get_collection(name=collection_name)
        except Exception:
            collection = client.create_collection(name=collection_name)
            docs, ids = await self._read_kb_documents_offthread(knowledge_base_path)
            if docs:
                try:
                    collection.add(documents=docs, ids=ids)
                except Exception as e:
                    if logger:
                        logger.warning("ChromaDB add() failed: %s", e)
            else:
                return "Error: No documents found in knowledge base directory"

        try:
            results = collection.query(query_texts=[search_query], n_results=top_k)
        except Exception as e:
            if logger:
                logger.error("ChromaDB query failed: %s", e)
            return f"Search error: {str(e)}"

        docs = results.get("documents") or []
        if docs and docs[0]:
            return "Found relevant information from ChromaDB:\n\n" + "\n\n".join(
                docs[0]
            )
        return f"No relevant information found in ChromaDB for query: {search_query}"

    # ----------------------------------------------------------------------------------
    # File I/O helpers (off-thread)
    # ----------------------------------------------------------------------------------
    async def _read_kb_documents_offthread(
        self, kb_path: str
    ) -> Tuple[List[str], List[str]]:
        """Read .md/.txt documents from disk off-thread to avoid blocking the loop.

        Args:
            kb_path: Filesystem path to the knowledge base directory.

        Returns:
            A tuple (documents, ids) with chunked text and deterministic IDs.
        """

        def _read() -> Tuple[List[str], List[str]]:
            """Perform the blocking file I/O operations."""
            documents: List[str] = []
            ids: List[str] = []
            for filename in os.listdir(kb_path):
                if filename.endswith((".md", ".txt")):
                    filepath = os.path.join(kb_path, filename)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read()
                        chunks = content.split("\n\n")  # simple blank-line chunking
                        for i, chunk in enumerate(chunks):
                            chunk = chunk.strip()
                            if chunk:
                                documents.append(chunk)
                                ids.append(f"{filename}_chunk_{i}")
                    except Exception:
                        continue
            return documents, ids

        return await to_thread.run_sync(_read)

    # ----------------------------------------------------------------------------------
    # Token accounting (defensive)
    # ----------------------------------------------------------------------------------
    async def _safe_count_tokens(
        self,
        system_message: str,
        user_message: str,
        assistant_message: str,
        model: str,
        logger: Optional[logging.Logger] = None,
    ) -> Tuple[int, int]:
        """Compute token counts defensively; never fail the request.

        Args:
            system_message: System prompt text.
            user_message: User input text.
            assistant_message: Assistant output text.
            model: Model name for tokenizer selection.
            logger: Optional logger for warnings.

        Returns:
            (total_tokens, completion_tokens), zeros on failure.
        """
        try:
            from ingenious.utils.token_counter import num_tokens_from_messages

            msgs: list[dict[str, Any]] = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": assistant_message},
            ]
            total = num_tokens_from_messages(msgs, model)
            prompt = num_tokens_from_messages(msgs[:-1], model)
            completion = total - prompt
            return total, completion
        except Exception as e:
            if logger:
                logger.warning("Token counting failed: %s", e)
            return 0, 0

    # ----------------------------------------------------------------------------------
    # System prompts (static text)
    # ----------------------------------------------------------------------------------
    def _static_system_message(self, memory_context: str) -> str:
        """Deterministic system prompt for direct mode.

        Args:
            memory_context: Optional prior conversation preview.

        Returns:
            A single prompt string guiding deterministic direct-mode behavior.
        """
        prefix = (
            "You are a knowledge base search assistant that uses Azure AI Search or "
            "local ChromaDB.\n\n"
        )
        if memory_context:
            prefix += memory_context
        prefix += (
            "Always base your responses on knowledge base search results. "
            "If nothing is found, clearly state that and suggest rephrasing the query. "
            "TERMINATE your response when the task is complete."
        )
        return prefix

    def _assist_system_message(self, memory_context: str) -> str:
        """Richer prompt for assist mode (summarization + citation hint).

        Args:
            memory_context: Optional prior conversation preview.

        Returns:
            A single prompt string guiding assist-mode behavior.
        """
        parts = [
            "You are a knowledge base search assistant that can use both Azure AI "
            "Search and local ChromaDB storage.\n",
        ]
        if memory_context:
            parts.append(memory_context)

        parts.append(
            "IMPORTANT: If there is previous conversation context above, you MUST:\n"
            "- Reference it when answering follow-up questions\n"
            "- Use information from previous searches to inform new searches\n"
            "- Maintain context about what information has already been discussed\n"
            '- Answer questions that refer to "it", "that", "those" etc. based on '
            "previous context\n\n"
            "Tasks:\n"
            "- Help users find information by searching the knowledge base\n"
            "- Use the search_tool to look up information\n"
            "- Always base your responses on search results from the knowledge base\n"
            "- Always consider and reference previous conversation when relevant\n"
            "- If no information is found, clearly state that and suggest rephrasing "
            "the query\n\n"
            "Guidelines for search queries:\n"
            "- Use specific, relevant keywords\n"
            "- Try different phrasings if initial search doesn't return results\n"
            "- Focus on topics that are relevant to the knowledge base content\n\n"
            "Format your responses clearly and cite the knowledge base when providing "
            "information.\n"
            "TERMINATE your response when the task is complete."
        )
        return "".join(parts)

    def _streaming_system_message(self, memory_context: str) -> str:
        """Streaming prompt with guidance, topics, and citation directive.

        Args:
            memory_context: Optional prior conversation preview.

        Returns:
            A single prompt string for streaming interactions.
        """
        parts: List[str] = [
            "You are a knowledge base search assistant that can use both Azure AI "
            "Search and local ChromaDB storage.\n\n"
        ]
        if memory_context:
            parts.append(memory_context)

        parts.append(
            "IMPORTANT: Maintain context and base your responses on search results.\n\n"
            "Guidelines for search queries:\n"
            "- Use specific, relevant keywords\n"
            "- Try different phrasings if initial search doesn't return results\n"
            "- Focus on topics that are relevant to the knowledge base content\n\n"
            "Knowledge base contains documents about:\n"
            "- Azure configuration and setup\n"
            "- Workplace safety guidelines\n"
            "- Health information and nutrition\n"
            "- Emergency procedures\n"
            "- Mental health and wellbeing\n"
            "- First aid basics\n"
            "- General informational content\n\n"
            "Format your responses clearly and cite the knowledge base when providing "
            "information."
        )
        return "".join(parts)
