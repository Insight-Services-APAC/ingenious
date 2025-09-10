from __future__ import annotations

"""Targeted tests for multi-agent service internals.

Why:
    Close a high-impact gap by ensuring content-filtered history is rejected
    early. This guards flow execution from unsafe prior messages.

Usage:
    `pytest -q tests/test_additional/test_multi_agent_content_filter.py`
"""

from types import SimpleNamespace
from typing import Any

import pytest

from ingenious.errors.content_filter_error import ContentFilterError
from ingenious.services.chat_services.multi_agent.service import (
    multi_agent_chat_service,
)

THREAD_ID: str = "t1"
USER_PROMPT: str = "hello"
FILTER_RESULT: dict[str, str] = {"violence": "high"}


@pytest.mark.asyncio
async def test_process_thread_messages_raises_on_content_filter_violation(
    make_min_multi_config: Any,
) -> None:
    """Raise on content-filtered history and avoid appending to chat history.

    Intent:
        `_process_thread_messages` must immediately raise `ContentFilterError`
        when any prior message has non-empty `content_filter_results`, and it
        must *not* append that message into `thread_chat_history`.

    Args:
        make_min_multi_config: Factory fixture providing a minimal config.
    """
    cfg = make_min_multi_config()
    svc = multi_agent_chat_service(  # type: ignore[arg-type]
        config=cfg,
        chat_history_repository=SimpleNamespace(),
        conversation_flow="classification_agent",
    )

    request = SimpleNamespace(
        thread_chat_history=[],
        user_prompt=USER_PROMPT,
        thread_id=THREAD_ID,
    )
    offending = SimpleNamespace(
        role="user", content="...", content_filter_results=FILTER_RESULT
    )

    with pytest.raises(ContentFilterError):
        await svc._process_thread_messages(request, [offending])  # type: ignore[arg-type]

    # Ensure nothing was appended as a side effect.
    assert request.thread_chat_history == []
