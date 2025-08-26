"""Test utility functions in the knowledge base agent conversation flow.

This module contains unit tests for helper methods within the ConversationFlow
class of the knowledge base agent. It specifically verifies the robustness of
the token counter and the correctness of secret handling utilities (unwrapping
and masking). These tests ensure that edge cases like tokenization failures and
different secret formats are handled gracefully without affecting the agent's
main logic.
"""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

import ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent.knowledge_base_agent as kb

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any, NoReturn

    from pytest import MonkeyPatch


@pytest.mark.asyncio
async def test_safe_count_tokens_returns_zero_on_failure(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Verify _safe_count_tokens returns (0, 0) when tokenization fails.

    This test ensures that if the underlying token counting utility raises an
    exception, the _safe_count_tokens method catches it and returns zero for
    both total and completion tokens, preventing crashes.
    """
    # Install a counter that raises
    tc = types.ModuleType("ingenious.utils.token_counter")

    def _boom(*a: Any, **k: Any) -> NoReturn:
        """A dummy function that always raises an error."""
        raise RuntimeError("fail")

    tc.num_tokens_from_messages = _boom
    monkeypatch.setitem(sys.modules, "ingenious.utils.token_counter", tc)

    # The class is instantiated without calling __init__ to isolate this method.
    flow: kb.ConversationFlow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    flow._config = SimpleNamespace(models=[SimpleNamespace(model="gpt-4o")])
    flow._chat_service = None
    flow._memory_path = str(tmp_path)
    total, comp = await flow._safe_count_tokens("s", "u", "a", "gpt-4o")
    assert (total, comp) == (0, 0)


def test_unwrap_secret_and_mask_secret_variants(tmp_path: Path) -> None:
    """Test the _unwrap_secret_or_str and _mask_secret helper methods.

    This test validates two utility functions:
    1. _unwrap_secret_or_str: Correctly extracts the string value from a
       secret-holding object or returns an empty string for None.
    2. _mask_secret: Correctly redacts secrets of different lengths for safe
       display.
    """
    # The class is instantiated without calling __init__ to isolate methods.
    flow: kb.ConversationFlow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    flow._config = SimpleNamespace(models=[SimpleNamespace(model="gpt-4o")])
    flow._chat_service = None
    flow._memory_path = str(tmp_path)

    class SecretObj:
        """A mock secret object with a value-retrieving method."""

        def get_secret_value(self) -> str:
            """Return the secret string."""
            return "abcd"

    assert flow._unwrap_secret_or_str(SecretObj()) == "abcd"
    assert flow._unwrap_secret_or_str(None) == ""

    # Mask short (<=8)
    assert flow._mask_secret("abcd") == "a***d"
    # Mask long (>8)
    masked: str = flow._mask_secret("abcdefghijklmnop")  # len=16
    assert masked.startswith("abcd...") and "(len=16)" in masked
    # No reveal bypass supported in the current implementation.
