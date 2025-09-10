"""Classification agent (v2 pattern) with native streaming support.

This module wires a higher-level classification pattern that can register
topic-focused agents from Jinja templates. It parses optional match payloads,
builds agent prompts, executes the coordinator, and returns a compact tuple
(result, memory_summary) for drop‑in back‑compat with existing services.
It now also exposes a **native streaming** method that emits:
status(preparing/generating) → delta/content* → usage → final.

Key entry points:
- ConversationFlow.get_conversation_response() -> tuple[str, str]
- ConversationFlow.get_streaming_conversation_response(...) -> AsyncIterator[ChatResponseChunk]
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

from jinja2 import Environment, FileSystemLoader

import ingenious.config.config as config
import ingenious.utils.match_parser as mp
from ingenious.models.chat import ChatRequest, ChatResponseChunk
from ingenious.services.chat_services.multi_agent.conversation_patterns.classification_agent.classification_agent_v2 import (  # noqa: E501
    ConversationPattern,
)

logger = logging.getLogger(__name__)

# ----------------------------- constants ----------------------------------- #
TEMPLATE_DIR_REL: str = "ingenious/templates/prompts"
DEFAULT_PAYLOAD: str = "payload undefined"
TOPIC_NAMES: list[str] = [
    "payload_type_1",
    "payload_type_2",
    "payload_type_3",
    "undefined",
]

# Streaming/status constants kept consistent with other agents.
STATUS_PREPARING: str = "Analyzing input and context..."
STATUS_GENERATING: str = "Generating classification..."
EVENT_TYPE_STREAMING: str = "classification_streaming"
SUMMARY_LIMIT: int = 200
MEMORY_PREVIEW_LIMIT: int = 100  # reserved if memory preview is ever added here
CHUNK_TARGET_CHARS: int = 320  # word-aware delta target size


def _topics_to_list(topics: str | list[str] | None) -> list[str]:
    """Return topics as a list for downstream use.

    Why: Maintain signature parity while supporting str, list[str], or None.
    """
    if isinstance(topics, str) and topics:
        return [topics]
    if isinstance(topics, list):
        return topics
    return []


def _chunk_text_by_words(text: str, target_chars: int) -> list[str]:
    """Split text near word boundaries without exceeding target size.

    Why: Provides user-friendly streaming deltas when only a final string
    is available (pattern does not expose incremental tokens).
    """
    if not text:
        return []
    parts: list[str] = []
    buf: list[str] = []
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


class ConversationFlow:
    """Classification flow for the v2 conversation pattern.

    The flow composes topic agents using Jinja templates (if present), falls
    back to a guardrail message when a template is missing, and returns a
    standard (result, memory_summary) tuple for service compatibility. It also
    exposes a native streaming method for consistent client UX.
    """

    @staticmethod
    async def get_conversation_response(chatrequest: ChatRequest) -> tuple[str, str]:
        """Return the classification response and memory summary using v2 pattern.

        Why: Keeps parity with existing service signatures while enabling
        multi‑topic classification logic via a higher-level pattern object.

        Args:
            chatrequest: Request DTO carrying prompt, topics, memory, and flags.

        Returns:
            A tuple of (result_text, memory_summary).
        """
        message = chatrequest.user_prompt
        topics = chatrequest.topic
        thread_memory = chatrequest.thread_memory
        memory_record_switch = chatrequest.memory_record
        event_type = chatrequest.event_type

        _config = config.get_config()
        llm_config: dict[str, object] = {
            "model": _config.models[0].model,
            "api_key": _config.models[0].api_key,
            "azure_endpoint": _config.models[0].base_url,
            "azure_deployment": _config.models[0].deployment,
            "api_version": _config.models[0].api_version,
            "api_type": "azure",
            "authentication_method": _config.models[0].authentication_method,
        }
        memory_path = _config.chat_history.memory_path

        # Load Jinja environment for prompts
        working_dir = Path(os.getcwd())
        template_path = working_dir / TEMPLATE_DIR_REL
        env = Environment(loader=FileSystemLoader(template_path), autoescape=True)

        # Parse optional match payload
        try:
            match = mp.MatchDataParser(payload=message, event_type=event_type)
            message, over_ball, timestamp, match_id, feed_id = (
                match.create_detailed_summary()
            )
        except Exception as parse_exc:
            logger.debug(
                "Match parsing failed; using fallback payload. Reason: %s", parse_exc
            )
            message = DEFAULT_PAYLOAD
            timestamp = str(datetime.now())
            match_id = "-"
            feed_id = "-"
            over_ball = "-"

        topics_list = _topics_to_list(topics)

        # Initialize the conversation pattern
        classification_pattern = ConversationPattern(
            default_llm_config=llm_config,
            topics=topics_list,
            memory_record_switch=bool(memory_record_switch),
            memory_path=memory_path,
            thread_memory=thread_memory or "",
        )

        response_id = str(uuid.uuid4())

        # Register topic agents (template if found, otherwise fallback)
        for topic in TOPIC_NAMES:
            try:
                template = env.get_template(f"{topic}_prompt.jinja")
                system_message = template.render(
                    topic=topic,
                    response_id=response_id,
                    feedTimestamp=timestamp,
                    match_id=match_id,
                    feedId=feed_id,
                    overBall=over_ball,
                )
            except Exception as tmpl_exc:
                logger.warning(
                    "Template for topic %s not found; using fallback. Reason: %s",
                    topic,
                    tmpl_exc,
                )
                system_message = (
                    "I **ONLY** respond when addressed by `planner`, "
                    f"focusing solely on insights about {topic}."
                    if topic != "undefined"
                    else "I **ONLY** respond when addressed by `planner` when the "
                    "payload is undefined."
                )
            classification_pattern.add_topic_agent(topic, system_message)

        try:
            result, memory_summary = await classification_pattern.get_conversation_response(
                message
            )
        finally:
            try:
                await classification_pattern.close()
            except Exception as close_exc:
                logger.debug("Pattern close failed: %s", close_exc)

        return result, memory_summary

    @staticmethod
    async def get_streaming_conversation_response(
        message: str,
        topics: list[str] | None = None,
        thread_memory: str = "",
        memory_record_switch: bool = True,  # kept for parity
        thread_chat_history: list[dict[str, str]] | None = None,  # unused here
        chatrequest: ChatRequest | None = None,
    ) -> AsyncIterator[ChatResponseChunk]:
        """Yield a native streaming classification with standardized usage chunks.

        Why: Mirrors other agents' streaming shapes to simplify client handling.
        Emits: status(preparing/generating) → delta* (word-aware) → usage → final.
        """
        # Prefer structured request when available
        user_text = message
        resolved_topics: list[str] | str | None = topics
        resolved_thread_memory = thread_memory
        resolved_memory_switch = memory_record_switch
        event_type = None
        thread_id = ""
        if chatrequest:
            user_text = chatrequest.user_prompt
            resolved_topics = chatrequest.topic
            resolved_thread_memory = chatrequest.thread_memory
            resolved_memory_switch = chatrequest.memory_record
            event_type = getattr(chatrequest, "event_type", None)
            thread_id = chatrequest.thread_id or ""

        message_id = str(uuid.uuid4())

        # --- Status: preparing/generating
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

        # Reuse the non-streaming logic to produce the final text, then stream it
        # as deltas (word-aware). This preserves behavior while offering streaming UX.
        _config = config.get_config()
        llm_config: dict[str, object] = {
            "model": _config.models[0].model,
            "api_key": _config.models[0].api_key,
            "azure_endpoint": _config.models[0].base_url,
            "azure_deployment": _config.models[0].deployment,
            "api_version": _config.models[0].api_version,
            "api_type": "azure",
            "authentication_method": _config.models[0].authentication_method,
        }
        memory_path = _config.chat_history.memory_path

        # Templates
        working_dir = Path(os.getcwd())
        template_path = working_dir / TEMPLATE_DIR_REL
        env = Environment(loader=FileSystemLoader(template_path), autoescape=True)

        # Parse optional match payload (same as non‑streaming)
        try:
            match = mp.MatchDataParser(payload=user_text, event_type=event_type)
            parsed_text, over_ball, timestamp, match_id, feed_id = (
                match.create_detailed_summary()
            )
        except Exception as parse_exc:
            logger.debug(
                "Match parsing failed; using fallback payload. Reason: %s", parse_exc
            )
            parsed_text = DEFAULT_PAYLOAD
            timestamp = str(datetime.now())
            match_id = "-"
            feed_id = "-"
            over_ball = "-"

        topics_list = _topics_to_list(resolved_topics)

        # Pattern init
        classification_pattern = ConversationPattern(
            default_llm_config=llm_config,
            topics=topics_list,
            memory_record_switch=bool(resolved_memory_switch),
            memory_path=memory_path,
            thread_memory=resolved_thread_memory or "",
        )

        response_id = str(uuid.uuid4())

        # Register topic agents (template if found, otherwise fallback)
        for topic in TOPIC_NAMES:
            try:
                template = env.get_template(f"{topic}_prompt.jinja")
                system_message = template.render(
                    topic=topic,
                    response_id=response_id,
                    feedTimestamp=timestamp,
                    match_id=match_id,
                    feedId=feed_id,
                    overBall=over_ball,
                )
            except Exception as tmpl_exc:
                logger.warning(
                    "Template for topic %s not found; using fallback. Reason: %s",
                    topic,
                    tmpl_exc,
                )
                system_message = (
                    "I **ONLY** respond when addressed by `planner`, "
                    f"focusing solely on insights about {topic}."
                    if topic != "undefined"
                    else "I **ONLY** respond when addressed by `planner` when the "
                    "payload is undefined."
                )
            classification_pattern.add_topic_agent(topic, system_message)

        # Produce the full text (pattern currently does not stream)
        try:
            full_text, memory_summary = await classification_pattern.get_conversation_response(
                parsed_text
            )
        finally:
            try:
                await classification_pattern.close()
            except Exception as close_exc:
                logger.debug("Pattern close failed: %s", close_exc)

        # Stream the full text in word-aware chunks (delta/content)
        for piece in _chunk_text_by_words(full_text, CHUNK_TARGET_CHARS):
            yield ChatResponseChunk(
                thread_id=thread_id,
                message_id=message_id,
                chunk_type="content",
                content=piece,
                is_final=False,
            )

        # Usage accounting (best effort)
        total_tokens = 0
        completion_tokens = 0
        try:
            from ingenious.utils.token_counter import num_tokens_from_messages

            total_tokens = int(
                num_tokens_from_messages(
                    [
                        {"role": "system", "content": ""},
                        {"role": "user", "content": user_text},
                        {"role": "assistant", "content": full_text},
                    ],
                    _config.models[0].model,
                )
            )
            prompt_tokens = int(
                num_tokens_from_messages(
                    [
                        {"role": "system", "content": ""},
                        {"role": "user", "content": user_text},
                    ],
                    _config.models[0].model,
                )
            )
            completion_tokens = max(0, total_tokens - prompt_tokens)
        except Exception as count_exc:
            logger.debug("Token count fallback failed: %s", count_exc)
            completion_tokens = max(0, len(full_text) // 4)
            total_tokens = max(0, (len(user_text) // 4) + completion_tokens)

        # Emit a standardized 'usage' chunk before final
        yield ChatResponseChunk(
            thread_id=thread_id,
            message_id=message_id,
            chunk_type="usage",
            token_count=total_tokens,
            max_token_count=completion_tokens,
            is_final=False,
        )

        # Finalize stream with memory summary
        summary = (
            memory_summary
            if len(memory_summary) <= SUMMARY_LIMIT
            else memory_summary[:SUMMARY_LIMIT] + "..."
        )
        yield ChatResponseChunk(
            thread_id=thread_id,
            message_id=message_id,
            chunk_type="final",
            token_count=total_tokens,
            max_token_count=completion_tokens,
            memory_summary=summary,
            event_type=EVENT_TYPE_STREAMING,
            is_final=True,
        )
