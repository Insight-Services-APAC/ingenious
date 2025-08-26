"""KB policy local_only: deterministic empty-dir message.

This test module verifies the behavior of the Knowledge Base (KB) agent's
ConversationFlow under a specific configuration. It ensures that when the
`KB_POLICY` environment variable is set to "local_only" and the specified
knowledge base directory does not exist or is empty, the agent returns a
predefined, user-friendly message instead of raising an error.

The test isolates the ConversationFlow by using dummy (stub) implementations for its
dependencies, such as the parent service and memory manager, ensuring the test
focuses solely on the intended logic path.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from ingenious.models.chat import ChatRequest

if TYPE_CHECKING:
    pass

# --- Constants for magic values ---
KB_POLICY_ENV_VAR = "KB_POLICY"
LOCAL_ONLY_POLICY = "local_only"
DUMMY_THREAD_ID = "thread-123"
DUMMY_USER_PROMPT = "What is x?"
EXPECTED_EMPTY_DIR_MESSAGE = "Knowledge base directory is empty"

DUMMY_MODEL_ROLE = "chat"
DUMMY_MODEL_NAME = "gpt"
DUMMY_API_ENDPOINT = "https://o"
DUMMY_API_KEY = "k"
DUMMY_API_VERSION = "2024-02-01"


class _DummyChatHistoryRepo:
    """A stub repository for chat history, returning no messages."""

    async def get_thread_messages(self, thread_id: str) -> list[SimpleNamespace]:
        """Simulate fetching chat messages, always returning an empty list.

        This is the minimal implementation required by the ConversationFlow's
        internal memory context builder.

        Args:
            thread_id: The ID of the conversation thread (unused).

        Returns:
            An empty list.
        """
        return []


class _DummyParentService:
    """A minimal stub for the parent multi-agent chat service."""

    def __init__(self, config: SimpleNamespace) -> None:
        """Initialize the dummy service with required attributes.

        Args:
            config: A mock configuration object.
        """
        self.config = config
        self.chat_history_repository = _DummyChatHistoryRepo()


@pytest.mark.asyncio
async def test_kb_policy_local_only_missing_dir_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify empty KB directory message when KB_POLICY is 'local_only'.

    This test sets up a scenario where the knowledge base policy is restricted
    to a local directory that is intentionally left non-existent. It then
    asserts that the ConversationFlow correctly identifies this state and
    returns a specific, deterministic message to the user, rather than failing.

    Args:
        tmp_path: A pytest fixture providing a temporary directory path.
        monkeypatch: A pytest fixture for modifying classes, methods, or env vars.
    """
    # Import locally to avoid potential circular dependencies at test discovery.
    from ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent.knowledge_base_agent import (
        ConversationFlow,
    )

    kb_dir = tmp_path / "kb_missing"
    assert not kb_dir.exists()

    # Force local-only policy via environment variable.
    monkeypatch.setenv(KB_POLICY_ENV_VAR, LOCAL_ONLY_POLICY)

    # ---- Stub the memory manager so the base service doesn't need file_storage ----
    class _DummyMemoryManager:
        """A placeholder class for the memory manager."""

        pass

    # The `mm` module is dynamically patched, confusing mypy.
    import ingenious.services.memory_manager as mm

    monkeypatch.setattr(
        mm,
        "get_memory_manager",
        lambda *_a, **_k: _DummyMemoryManager(),
        raising=True,
    )

    # Minimal config object the flow expects.
    cfg = SimpleNamespace(
        models=[
            SimpleNamespace(
                role=DUMMY_MODEL_ROLE,
                model=DUMMY_MODEL_NAME,
                deployment=DUMMY_MODEL_NAME,
                endpoint=DUMMY_API_ENDPOINT,
                api_key=DUMMY_API_KEY,
                api_version=DUMMY_API_VERSION,
            )
        ],
        azure_search_services=[],
    )
    memory_path = tmp_path / "mem"
    memory_path.mkdir(parents=True, exist_ok=True)
    cfg.chat_history = SimpleNamespace(memory_path=str(memory_path))

    # Provide the required parent service stub.
    parent = _DummyParentService(cfg)
    flow = ConversationFlow(
        parent_multi_agent_chat_service=parent,
        knowledge_base_path=str(kb_dir),
    )

    req = ChatRequest(
        thread_id=DUMMY_THREAD_ID,
        user_prompt=DUMMY_USER_PROMPT,
        parameters={},
    )
    resp = await flow.get_conversation_response(req)
    assert EXPECTED_EMPTY_DIR_MESSAGE in resp.agent_response
