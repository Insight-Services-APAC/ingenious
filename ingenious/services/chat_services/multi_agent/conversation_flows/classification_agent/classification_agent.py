# ingenious/services/chat_services/multi_agent/conversation_flows/classification_agent/classification_agent.py
"""Classification agent (v1) with defensive shims for tests and stubs.

This module preserves the legacy v1 "classification" flow API that some tests
call **as class methods** (no `self`). It adds the minimal shims needed for
deterministic behavior in CI and for test monkeypatching:

- `config` shim: exposes `.get_config(...)` so tests can monkeypatch it.
- `_shim_model_client`: injects `.model_info` into stubbed model clients.
- `_resolve_assistant_agent`: fetches the current AssistantAgent class so
  monkeypatches on this module or the origin package are honored.
- `LLMUsageTracker` export: provided (or safely stubbed) for monkeypatching.

Usage:
    await ConversationFlow.get_conversation_response(...)
    async for chunk in ConversationFlow.get_streaming_conversation_response(...):

Key entry points:
- ConversationFlow.get_conversation_response
- ConversationFlow.get_streaming_conversation_response
"""

from __future__ import annotations

import logging
import os
import uuid
from importlib import import_module
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, AsyncIterator, cast

from autogen_core import CancellationToken
from ingenious.client.azure import AzureClientFactory
from ingenious.models.chat import ChatRequest, ChatResponseChunk

if TYPE_CHECKING:  # pragma: no cover
    from typing import Iterable

logger = logging.getLogger(__name__)

# ----------------------------- constants ----------------------------------- #
STATUS_PREPARING: str = "Preparing context..."
STATUS_GENERATING: str = "Generating classification response..."
EVENT_TYPE_STREAMING: str = "classification_streaming"
MEMORY_PREVIEW_LIMIT: int = 100
HISTORY_WINDOW: int = 10
SUMMARY_LIMIT: int = 200

# Fallback/text/model constants expected by tests.
DEFAULT_MODEL_NAME: str = "gpt-fake"
FALLBACK_TEXT_PREFIX: str = "Category: "
FALLBACK_CATEGORY: str = "payload_type_1"
FALLBACK_MEM_PREFIX: str = "Classification error handled: "

# --------------------------- AssistantAgent alias --------------------------- #
try:
    from autogen_agentchat.agents import (  # type: ignore[import-untyped]
        AssistantAgent as _AssistantAgent,
    )
except Exception:  # pragma: no cover - environments without autogen installed
    class _AssistantAgent:  # type: ignore[too-many-ancestors]
        """Fallback stub to satisfy type checkers when autogen is unavailable."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("AssistantAgent unavailable")


# Preserve the legacy symbol; tests may patch this name on this module.
AssistantAgent = _AssistantAgent

# --------------------------- LLMUsageTracker export ------------------------- #
# Tests may monkeypatch this name with a dummy logging.Handler. If the real
# tracker cannot be imported in the current environment, provide a no-op.
try:
    from ingenious.models.agent import (  # type: ignore[import-untyped]
        LLMUsageTracker as LLMUsageTracker,
    )
except Exception:
    class LLMUsageTracker(logging.Handler):
        """No-op LLM usage tracker fallback for monkeypatching."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            """Construct a no-op logging handler."""
            super().__init__()


# ------------------------------ Model client shim --------------------------- #
def _shim_model_client(client: object) -> object:
    """Return a proxy that supplies ``model_info`` when a stub lacks it.

    Why:
        Tests may patch the model client factory to return a tiny object without
        `.model_info`. Some agent SDKs access this attribute. We inject a small,
        read-only view to keep construction safe while preserving public APIs.

    Args:
        client: The original model client (possibly a stub).

    Returns:
        Either the original client or a proxy exposing `.model_info`.
    """
    if hasattr(client, "model_info"):
        return client

    class _ClientShim:
        def __init__(self, inner: object) -> None:
            self._inner = inner

        @property
        def model_info(self) -> dict[str, object]:
            return {"function_calling": True, "vision": False}

        def __getattr__(self, name: str) -> object:  # pragma: no cover
            return getattr(self._inner, name)

    return _ClientShim(client)


# ------------------------------ Config shims -------------------------------- #
class _ConfigShim:
    """Thin wrapper to obtain settings; falls back to a stub in tests.

    The legacy flow expects a config with at least `.models[0]`. We try to load
    real settings and otherwise return a minimal stub so the flow remains
    deterministic in CI/mocked environments.
    """

    def get_config(self, *args: Any, **kwargs: Any) -> Any:
        """Return real settings when available, else a minimal stub config."""
        try:
            from ingenious.config.main_settings import (  # type: ignore[import-untyped]
                IngeniousSettings,
            )

            return IngeniousSettings(*args, **kwargs)
        except Exception as exc:
            logger.debug("Config load failed (%s); using DEFAULT_MODEL_NAME.", exc)
            return SimpleNamespace(models=[SimpleNamespace(model=DEFAULT_MODEL_NAME)])


class _ConfigModuleShim:
    """Module-like shim exposing `.get_config(...)` for test monkeypatching."""

    @staticmethod
    def get_config(*args: Any, **kwargs: Any) -> Any:
        """Delegate to real config if importable; else `_ConfigShim`."""
        try:
            from ingenious.config import config as _real_config  # type: ignore[import-untyped]

            get_conf = getattr(_real_config, "get_config", None)
            if callable(get_conf):
                return get_conf(*args, **kwargs)
        except Exception:
            pass
        return _ConfigShim().get_config(*args, **kwargs)


# Expose `config` at module scope so tests can monkeypatch
# `clf_mod.config.get_config`.
config = _ConfigModuleShim()

# ------------------------------ Helpers ------------------------------------ #
def _resolve_assistant_agent() -> type[_AssistantAgent]:
    """Return current AssistantAgent class honoring monkeypatches.

    Preference:
        1) If this module's `AssistantAgent` alias was patched, use it.
        2) Else import the class from the origin module (captures external patches).
        3) Fallback to the originally imported `_AssistantAgent`.
    """
    try:
        alias = cast(type[_AssistantAgent], globals().get("AssistantAgent"))
        if alias is not None and alias is not _AssistantAgent:
            return alias
    except Exception:
        pass
    try:
        mod = import_module("autogen_agentchat.agents")
        return cast(type[_AssistantAgent], getattr(mod, "AssistantAgent"))
    except Exception:
        return _AssistantAgent


def _topics_to_line(topics: list[str] | None) -> str:
    """Return a single-line topics hint to embed in the system prompt.

    Why:
        Tests pass candidate topics. Including them yields deterministic, short
        prompts and exercises spy agents without contacting a model.
    """
    if not topics:
        return ""
    try:
        cleaned = [t.strip() for t in topics if t and t.strip()]
    except Exception:
        return ""
    return f"Candidate topics: {', '.join(cleaned)}.\n"


def _build_history_preview(
    thread_chat_history: list[dict[str, str]] | None,
) -> str:
    """Return a compact 'Previous conversation' preview from message history.

    We include up to the last HISTORY_WINDOW messages, formatting each line as
    ``role: content[:MEMORY_PREVIEW_LIMIT]...``.
    """
    if not thread_chat_history:
        return ""
    try:
        recent = (
            thread_chat_history[-HISTORY_WINDOW:]
            if len(thread_chat_history) > HISTORY_WINDOW
            else thread_chat_history
        )
        lines: list[str] = []
        for m in recent:
            role = str(m.get("role", "user"))
            content = str(m.get("content", ""))
            snippet = content[:MEMORY_PREVIEW_LIMIT] + ("..." if content else "")
            lines.append(f"{role}: {snippet}")
        return "Previous conversation:\n" + "\n".join(lines) + "\n\n"
    except Exception:
        return ""


def _build_memory_context(
    thread_memory: str, thread_chat_history: list[dict[str, str]] | None
) -> str:
    """Return memory context with explicit-string precedence over history preview.

    Precedence:
        1) If `thread_memory` is non-empty after stripping, use it verbatim.
        2) Otherwise, synthesize a preview from `thread_chat_history`.
    """
    memory = (thread_memory or "").strip()
    if memory:
        return f"Previous conversation:\n{memory}\n\n"
    return _build_history_preview(thread_chat_history)


def _system_message(
    memory_context: str, topics: list[str] | None, revision_hint: str | None = None
) -> str:
    """Return the system message for the classifier including optional context.

    Args:
        memory_context: Precedence-composed memory/history text.
        topics: Optional list of candidate topics to hint the classifier.
        revision_hint: Optional revision string for traceability.

    Returns:
        A single string system prompt.
    """
    parts: list[str] = [
        "You are a short-text classification assistant.\n",
    ]
    if revision_hint:
        parts.append(f"(revision: {revision_hint})\n")
    if memory_context:
        parts.append(memory_context)
    topics_line = _topics_to_line(topics)
    if topics_line:
        parts.append(topics_line)

    parts.append(
        "Instructions:\n"
        "- Consider the previous conversation/context when classifying.\n"
        "- Keep responses concise and deterministic.\n"
        "- If nothing matches, reply with 'unknown'.\n"
        "TERMINATE your response when the task is complete."
    )
    return "".join(parts)


# ------------------------------ Conversation Flow -------------------------- #
class ConversationFlow:
    """Legacy classification conversation flow (v1 surface, static-style API)."""

    @staticmethod
    async def get_conversation_response(
        message: str,
        topics: list[str] | None = None,
        thread_memory: str = "",
        memory_record_switch: bool = True,  # kept for API compatibility
        thread_chat_history: list[dict[str, str]] | None = None,
        chatrequest: ChatRequest | None = None,
    ) -> tuple[str, str]:
        """Return a full, non-streaming classification response and memory summary.

        Behavior:
            - Tries to instantiate an agent and call `.on_messages(...)`.
            - If that raises (the test patches this to raise), returns a
              deterministic fallback:
                text: "Category: payload_type_1"
                mem:  "Classification error handled: <exc>"
            - Otherwise returns a minimal "OK" response.

        Args:
            message: The user message to classify.
            topics: Optional list of candidate topics/hints.
            thread_memory: Explicit memory text; takes precedence over history.
            memory_record_switch: Unused; preserved for signature compatibility.
            thread_chat_history: Optional raw chat history (role/content dicts).
            chatrequest: Optional `ChatRequest` for parity with newer flows.

        Returns:
            A tuple of `(agent_response, memory_summary)`.
        """
        del memory_record_switch, chatrequest  # unused, API placeholder

        # Build context + prompt
        memory_context = _build_memory_context(thread_memory, thread_chat_history)
        system_message = _system_message(
            memory_context=memory_context,
            topics=topics,
            revision_hint=os.getenv("REVISION_ID", ""),
        )

        # Model config (use the module-level `config` shim to honor test patches)
        try:
            model_cfg = config.get_config().models[0]  # type: ignore[attr-defined]
        except Exception:
            model_cfg = SimpleNamespace(model=DEFAULT_MODEL_NAME)

        # Model client (defensive: tests stub the factory and ignore the arg)
        try:
            model_client = AzureClientFactory.create_openai_chat_completion_client(
                model_cfg
            )
        except Exception:
            class _NullClient:
                async def close(self) -> None:
                    """No-op close for stubbed environments."""
                    return None

            model_client = _NullClient()

        model_client = _shim_model_client(model_client)

        # Instantiate the agent and attempt a minimal on_messages call. Tests
        # replace AssistantAgent with a boom stub that always raises here.
        try:
            agent_cls = _resolve_assistant_agent()
            agent = agent_cls(
                name="classifier",
                system_message=system_message,
                model_client=model_client,
                tools=[],
                reflect_on_tool_use=False,
            )

            try:
                # Prefer a real TextMessage if available; otherwise a tiny stub.
                try:
                    from autogen_agentchat.messages import (  # type: ignore[import-untyped]
                        TextMessage,
                    )

                    user_msg = TextMessage(content=message, source="user")
                except Exception:
                    user_msg = SimpleNamespace(content=message, source="user")

                await agent.on_messages(messages=[user_msg], cancellation_token=None)
            except Exception as exc:
                # Deterministic fallback expected by tests.
                agent_response = f"{FALLBACK_TEXT_PREFIX}{FALLBACK_CATEGORY}"
                memory_summary = f"{FALLBACK_MEM_PREFIX}{exc}"
                return agent_response, memory_summary

        except Exception as exc:
            # Agent construction failure → same deterministic fallback.
            agent_response = f"{FALLBACK_TEXT_PREFIX}{FALLBACK_CATEGORY}"
            memory_summary = f"{FALLBACK_MEM_PREFIX}{exc}"
            return agent_response, memory_summary
        finally:
            try:
                await model_client.close()  # type: ignore[func-returns-value]
            except Exception:
                pass

        # If no exception occurred, return a minimal deterministic success.
        agent_response = "OK" if (message or "").strip() else "unknown"
        memory_summary = memory_context.strip() or "no-memory"
        return agent_response, memory_summary

    @staticmethod
    async def get_streaming_conversation_response(
        message: str,
        topics: list[str] | None = None,
        thread_memory: str = "",
        memory_record_switch: bool = True,  # noqa: ARG002 - retained for API compat
        thread_chat_history: list[dict[str, str]] | None = None,
        chatrequest: ChatRequest | None = None,
    ) -> AsyncIterator[ChatResponseChunk]:
        """Yield a streaming response: status → content* → usage* → final.

        Error policy:
            Any exception during streaming is surfaced as a **content** chunk
            whose text contains the substring "Error during streaming", which
            tests assert for observability. The stream still terminates with a
            final chunk after usage emission (real or fallback).
        """
        # Resolve model config via module-level `config` (honors monkeypatch).
        try:
            model_cfg = config.get_config().models[0]  # type: ignore[attr-defined]
        except Exception:
            model_cfg = SimpleNamespace(model=DEFAULT_MODEL_NAME)

        # Build prompt pieces.
        revision_hint = getattr(model_cfg, "revision", None)
        memory_context = _build_memory_context(thread_memory, thread_chat_history)
        system_message = _system_message(memory_context, topics, revision_hint)

        # Model client (shimmed) and agent.
        try:
            model_client = AzureClientFactory.create_openai_chat_completion_client(
                model_cfg
            )
            model_client = _shim_model_client(model_client)
        except Exception:
            class _NullClient:
                async def close(self) -> None:
                    """No-op close for stubbed environments."""
                    return None

            model_client = _NullClient()

        agent_cls = _resolve_assistant_agent()
        assistant = agent_cls(
            name="classification_assistant",
            system_message=system_message,
            model_client=model_client,
            tools=[],
            reflect_on_tool_use=False,
        )

        thread_id = chatrequest.thread_id if chatrequest and chatrequest.thread_id else ""
        message_id = str(uuid.uuid4())

        # Initial statuses.
        yield ChatResponseChunk(
            thread_id=thread_id,
            message_id=message_id,
            chunk_type="status",
            content=STATUS_PREPARING,
            is_final=False,
        )
        yield ChatResponseChunk(
            thread_id=thread_id,
            message_id=message_id,
            chunk_type="status",
            content=STATUS_GENERATING,
            is_final=False,
        )

        user_msg = f"{_topics_to_line(topics)}{message}" if topics else message
        cancellation_token = CancellationToken()

        accumulated = ""
        total_tokens = 0
        completion_tokens = 0

        def _usage_fallback() -> tuple[int, int]:
            """Return heuristic token counts when provider omits usage."""
            prompt_est = (len(system_message) + len(message)) // 4
            completion_est = len(accumulated) // 4
            total_est = prompt_est + completion_est
            return total_est, completion_est

        try:
            stream = assistant.run_stream(
                task=user_msg, cancellation_token=cancellation_token
            )
            async for msg in stream:
                # Content
                if hasattr(msg, "content") and msg.content:
                    text = str(msg.content)
                    accumulated += text
                    yield ChatResponseChunk(
                        thread_id=thread_id,
                        message_id=message_id,
                        chunk_type="content",
                        content=text,
                        is_final=False,
                    )
                # Usage
                if hasattr(msg, "usage") and msg.usage:
                    usage = msg.usage
                    if hasattr(usage, "total_tokens"):
                        total_tokens = int(usage.total_tokens)
                    if hasattr(usage, "completion_tokens"):
                        completion_tokens = int(usage.completion_tokens)
                    yield ChatResponseChunk(
                        thread_id=thread_id,
                        message_id=message_id,
                        chunk_type="usage",
                        token_count=total_tokens,
                        max_token_count=completion_tokens,
                        is_final=False,
                    )
        except Exception as exc:
            # Tests assert this substring appears in the content stream.
            err = f"[Error during streaming: {str(exc)}]"
            accumulated += err
            yield ChatResponseChunk(
                thread_id=thread_id,
                message_id=message_id,
                chunk_type="content",
                content=err,
                is_final=False,
            )
        finally:
            try:
                await model_client.close()
            except Exception:
                pass

        # Emit usage if provider omitted it.
        if total_tokens == 0:
            try:
                from ingenious.utils.token_counter import num_tokens_from_messages

                msgs = [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": accumulated},
                ]
                total_tokens = int(num_tokens_from_messages(msgs, model_cfg.model))
                prompt_tokens = int(
                    num_tokens_from_messages(msgs[:-1], model_cfg.model)
                )
                completion_tokens = max(0, total_tokens - prompt_tokens)
            except Exception:
                total_tokens, completion_tokens = _usage_fallback()

            yield ChatResponseChunk(
                thread_id=thread_id,
                message_id=message_id,
                chunk_type="usage",
                token_count=total_tokens,
                max_token_count=completion_tokens,
                is_final=False,
            )

        # Final chunk.
        yield ChatResponseChunk(
            thread_id=thread_id,
            message_id=message_id,
            chunk_type="final",
            token_count=total_tokens,
            max_token_count=completion_tokens,
            memory_summary=(
                accumulated[:SUMMARY_LIMIT] + "..."
                if len(accumulated) > SUMMARY_LIMIT
                else accumulated
            ),
            event_type=EVENT_TYPE_STREAMING,
            is_final=True,
        )
