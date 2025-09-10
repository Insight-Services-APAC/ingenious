"""Additional ChatService initialization error branches.

These tests exercise the remaining exception branches in ChatService.__init__:
- AttributeError → "Chat service class not found in module" with context.
- Generic Exception → "Unexpected error during chat service initialization"
  with a recovery suggestion in the error object.

Why:
Covers rare-but-important initialization failures so they surface as
ChatServiceError with actionable context, closing a remaining gap.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from ingenious.errors import ChatServiceError
from ingenious.services.chat_service import ChatService

SERVICE_TYPE_X: str = "X"
SERVICE_TYPE_Y: str = "Y"
CONVERSATION_FLOW: str = "flow"


class _Repo:
    """Minimal fake repository; never used due to early init failures."""

    async def add_message(self, _msg: Any) -> str:
        """Return a dummy id; this path is not reached in these tests."""
        return "id"

    async def add_memory(self, _msg: Any) -> str:
        """Return a dummy id; this path is not reached in these tests."""
        return "id"

    async def get_thread_messages(self, _tid: str) -> list[Any]:
        """Return no messages; not used in these tests."""
        return []


class _Cfg:
    """Minimal config stub satisfying constructor signature."""

    openai_service_instance: object = object()


@pytest.mark.anyio
async def test_chat_service_attribute_error_maps_to_chatserviceerror_with_context() -> None:
    """AttributeError path yields ChatServiceError with expected context fields."""
    with patch(
        "ingenious.services.chat_service.import_class_with_fallback",
        side_effect=AttributeError("missing class"),
    ):
        with pytest.raises(ChatServiceError) as exc:
            ChatService(
                chat_service_type=SERVICE_TYPE_X,
                chat_history_repository=_Repo(),
                conversation_flow=CONVERSATION_FLOW,
                config=_Cfg(),  # type: ignore[arg-type]
            )
    # Message is precise for AttributeError branch.
    assert "Chat service class not found in module" in str(exc.value)

    # Context is present and includes diagnostic keys.
    ctx = getattr(exc.value, "context", {})
    assert isinstance(ctx, dict)
    assert ctx.get("service_type") == SERVICE_TYPE_X
    assert ctx.get("module_name") is not None
    assert ctx.get("expected_class", "").endswith("_chat_service")


@pytest.mark.anyio
async def test_chat_service_unexpected_error_maps_to_chatserviceerror_with_suggestion() -> None:
    """Generic Exception path yields ChatServiceError with recovery suggestion."""
    with patch(
        "ingenious.services.chat_service.import_class_with_fallback",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(ChatServiceError) as exc:
            ChatService(
                chat_service_type=SERVICE_TYPE_Y,
                chat_history_repository=_Repo(),
                conversation_flow=CONVERSATION_FLOW,
                config=_Cfg(),  # type: ignore[arg-type]
            )
    msg = str(exc.value)
    assert "Unexpected error during chat service initialization" in msg

    # Recovery suggestion should guide the operator.
    suggestion = getattr(exc.value, "recovery_suggestion", "")
    assert "configuration and dependencies" in str(suggestion)
