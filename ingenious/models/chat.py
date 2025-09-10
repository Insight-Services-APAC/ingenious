"""Chat request/response data models for the chat service.

This module defines the Pydantic models used across the chat API surface,
including the request/response DTOs, streaming chunk/envelope types, and
several small helper models. It intentionally keeps the models lightweight
and compatible with both non‑streaming and streaming flows.

Why:
- Tests construct `ChatRequest(topic=["general"])`; we therefore accept
  `str | list[str] | None` for `topic` and leave normalization to services.
- Streaming flows use several chunk types; we enumerate the current superset.
- Defaults are chosen to be safe in tests (e.g., empty containers via
  `default_factory`, optional IDs for backfilling).

Usage:
- Use `ChatRequest` / `ChatResponse` for one‑shot calls.
- Use `ChatResponseChunk` within `StreamingChatResponse(event="data")` frames.
- SSE envelopes use events: `"data" | "error" | "done"`.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class IChatRequest(BaseModel):
    """Incoming chat request payload (shared interface).

    What:
        Carries the user's prompt, thread identifiers, optional memory flags,
        and flow selection. Designed to be permissive so tests and different
        services can supply only the fields they need.

    Notes:
        `topic` accepts `str | list[str] | None`. Downstream services may
        coerce this to a list or string as appropriate.
    """

    thread_id: str | None = None
    user_prompt: str
    event_type: str | None = None
    user_id: str | None = None
    user_name: str | None = None
    topic: str | list[str] | None = None
    memory_record: bool | None = True
    conversation_flow: str | None = None
    thread_chat_history: list[dict[str, str]] | None = Field(default_factory=list)
    thread_memory: str | None = None
    stream: bool | None = False
    kb_top_k: int | None = None
    parameters: dict[str, Any] | None = None

    @field_validator("topic")
    @classmethod
    def _normalize_topic(
        cls, v: str | list[str] | None
    ) -> str | list[str] | None:
        """Allow str/list; normalize empty string to None.

        Why:
            Tests may pass a list; services may later coerce to list-of-str.
        """
        if isinstance(v, str) and not v.strip():
            return None
        return v


class IChatResponse(BaseModel):
    """Synchronous chat response payload (shared interface).

    What:
        Holds the assistant response and related metadata. Fields are optional
        to allow partial/fallback responses in test doubles.
    """

    thread_id: str | None
    message_id: str | None
    agent_response: str | None
    followup_questions: dict[str, str] = Field(default_factory=dict)
    token_count: int | None
    max_token_count: int | None
    topic: str | None = None
    memory_summary: str | None = None
    event_type: str | None = None


class ChatRequest(IChatRequest):
    """Concrete chat request model (alias for interface)."""


class ChatResponse(IChatResponse):
    """Concrete chat response model (alias for interface)."""


class Action(BaseModel):
    """Lightweight action descriptor used by some flows/tools."""

    name: str
    description: str | None = None


class KnowledgeBaseLink(BaseModel):
    """Represents a link in KB-derived responses."""

    title: str
    url: str
    description: str | None = None


class Product(BaseModel):
    """Simple product schema for tool/demo responses."""

    name: str
    description: str | None = None
    price: float | None = None


_ChunkType = Literal[
    "content",
    "final",
    "status",
    "usage",
    "delta",
    "summary",
    "error",
]


class ChatResponseChunk(BaseModel):
    """A single piece of a streaming chat response.

    What:
        Chunks carry incremental content/status/usage information. A terminal
        `"final"` chunk conveys summary metadata and marks completion within
        the chat-service layer (the SSE envelope still ends with `event="done"`).

    Fields:
        chunk_type: One of: "content", "final", "status", "usage",
                    "delta", "summary", "error".
        is_final:  True only for the terminal "final" chunk at the flow layer.
    """

    thread_id: str | None
    message_id: str | None
    chunk_type: _ChunkType
    content: str | None = None
    token_count: int | None = None
    max_token_count: int | None = None
    topic: str | None = None
    memory_summary: str | None = None
    followup_questions: dict[str, str] | None = None
    event_type: str | None = None
    is_final: bool = False


class StreamingChatResponse(BaseModel):
    """SSE envelope for streaming chat endpoints.

    What:
        Frames streaming data as `"data"` (with `ChatResponseChunk`), `"error"`
        (with a string message), or `"done"` (no payload) for client cleanup.
    """

    event: Literal["data", "error", "done"]
    data: ChatResponseChunk | None = None
    error: str | None = None
