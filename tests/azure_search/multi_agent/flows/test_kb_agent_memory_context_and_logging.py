"""Tests memory context building and logging for the Knowledge Base Agent.

This module contains tests for the `_build_memory_context` method within the
Knowledge Base Agent's conversation flow. It specifically verifies:
1.  Correct truncation of the conversation history to the last 10 messages.
2.  Truncation of individual long messages to 100 characters.
3.  Throttling of warning logs when fetching chat history fails repeatedly,
    preventing log spam.

Tests use pytest fixtures like `monkeypatch`, `tmp_path`, and `caplog` to
isolate behavior and inspect outcomes.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, NoReturn

import pytest

import ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent.knowledge_base_agent as kb
from ingenious.models.chat import ChatRequest

if TYPE_CHECKING:
    from logging import LogRecord
    from pathlib import Path

    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch


@pytest.mark.asyncio
async def test_memory_context_truncates_last_10_and_100_chars(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """Verify memory context truncates history to the last 10 messages and long messages to 100 chars."""
    # Prepare 12 messages, one of them long (>100 chars)
    msgs: list[SimpleNamespace] = []
    for i in range(12):
        content: str = (f"msg{i}-" + "X" * 120) if i == 11 else f"msg{i}"
        msgs.append(SimpleNamespace(role="user", content=content))

    async def _get_thread_messages(tid: str) -> list[SimpleNamespace]:
        """Mock message retrieval to return the predefined list."""
        return msgs

    repo: SimpleNamespace = SimpleNamespace(get_thread_messages=_get_thread_messages)
    svc: SimpleNamespace = SimpleNamespace(chat_history_repository=repo)

    flow: kb.ConversationFlow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    flow._config = SimpleNamespace(models=[SimpleNamespace(model="gpt-5")])
    flow._chat_service = svc
    flow._memory_path = str(tmp_path)

    ctx: str = await flow._build_memory_context(ChatRequest(user_prompt="q", thread_id="t1"))

    # Only last 10 messages (drop msg0 and msg1); avoid 'msg1' vs 'msg10' collision
    assert "user: msg0..." not in ctx
    assert "user: msg1..." not in ctx
    assert "user: msg2..." in ctx and "user: msg11" in ctx
    # Long one is truncated to first 100 chars (including the 'msg11-' prefix), then "..."
    long_prefix: str = "msg11-"
    expected_trunc: str = long_prefix + ("X" * (100 - len(long_prefix)))
    assert (expected_trunc + "...") in ctx
    assert ctx.startswith("Previous conversation:\n")


@pytest.mark.asyncio
async def test_memory_warning_throttled_to_once_within_60s(
    monkeypatch: MonkeyPatch, caplog: LogCaptureFixture, tmp_path: Path
) -> None:
    """Verify memory retrieval failure warnings are throttled to once per 60 seconds."""

    async def _always_fail(_tid: str) -> NoReturn:
        """Mock message retrieval to always raise an exception."""
        raise RuntimeError("db down")

    repo: SimpleNamespace = SimpleNamespace(get_thread_messages=_always_fail)
    svc: SimpleNamespace = SimpleNamespace(chat_history_repository=repo)

    flow: kb.ConversationFlow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    flow._config = SimpleNamespace(models=[SimpleNamespace(model="gpt-5")])
    flow._chat_service = svc
    flow._memory_path = str(tmp_path)

    # Freeze time so second call occurs within < 60s of the first
    t: list[float] = [1000.0]
    monkeypatch.setattr(kb.time, "monotonic", lambda: t[0])

    req: ChatRequest = ChatRequest(user_prompt="q", thread_id="t1")

    # IMPORTANT: force the exact logger used by _build_memory_context to DEBUG
    kb_logger_name: str = f"{kb.EVENT_LOGGER_NAME}.kb"
    kb_logger: logging.Logger = logging.getLogger(kb_logger_name)
    kb_logger.propagate = True  # ensure records bubble up
    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger=kb_logger_name):
        _ = await flow._build_memory_context(req)  # first call -> WARNING
        t[0] = 1010.0  # +10s, still within throttle window
        _ = await flow._build_memory_context(req)  # second call -> DEBUG "(suppressed)"

    warns: list[LogRecord] = [
        r for r in caplog.records if r.levelno >= logging.WARNING and r.name == kb_logger_name
    ]
    debugs: list[LogRecord] = [
        r for r in caplog.records if r.levelno == logging.DEBUG and r.name == kb_logger_name
    ]

    assert any("Failed to retrieve thread memory:" in r.getMessage() for r in warns)
    assert any("suppressed" in r.getMessage() for r in debugs)
