"""KB preflight: classify factory ImportError as sdk_missing.

This test exercises the branch in `_preflight_azure_index_async` where the
client factory import fails (ImportError). The flow should raise a
PreflightError with reason == "sdk_missing".
"""

from __future__ import annotations

import sys
import types
from unittest.mock import patch

import pytest

from ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent.knowledge_base_agent import (  # noqa: E501
    ConversationFlow,
)
from ingenious.services.chat_services.multi_agent.service import (
    multi_agent_chat_service as _Parent,
)
from ingenious.services.retrieval.errors import PreflightError

ENDPOINT: str = "https://example"
INDEX_NAME: str = "idx"
KEY_VALUE: str = "secret-key"

from types import SimpleNamespace

class _Cfg:
    class ChatHistory:
        memory_path = "/tmp/test"

    class Azure:
        def __init__(self) -> None:
            self.search = SimpleNamespace(
                endpoint="x", index_name="y", key=SimpleNamespace(get_secret_value=lambda: "z")
            )

    def __init__(self) -> None:
        self.chat_history = self.ChatHistory()
        self.azure = self.Azure()
        # Add this line
        self.file_storage = SimpleNamespace(data=SimpleNamespace())

def _stub_parent() -> _Parent:
    """Create a minimal parent service for the flow."""
    repo = types.SimpleNamespace(
        add_message=lambda *_: "id",
        add_memory=lambda *_: "id",
        get_thread_messages=lambda *_: [],
    )
    return _Parent(config=_Cfg(), chat_history_repository=repo, conversation_flow="kb")


@pytest.mark.anyio
async def test_kb_preflight_factory_import_missing_maps_to_sdk_missing() -> None:
    """Factory ImportError is mapped to PreflightError(reason='sdk_missing')."""
    # Ensure azure.search.documents.aio.SearchClient import succeeds first.
    aio_mod = types.ModuleType("azure.search.documents.aio")
    aio_mod.SearchClient = object  # type: ignore[attr-defined]
    sys.modules["azure"] = types.ModuleType("azure")
    sys.modules["azure.search"] = types.ModuleType("azure.search")
    sys.modules["azure.search.documents"] = types.ModuleType("azure.search.documents")
    sys.modules["azure.search.documents.aio"] = aio_mod

    # Patch the factory to raise ImportError to trigger sdk_missing path.
    with patch(
        "ingenious.services.azure_search.client_init.make_async_search_client",
        side_effect=ImportError("no client factory"),
    ):
        flow = ConversationFlow(parent_multi_agent_chat_service=_stub_parent())
        coro = flow._require_valid_azure_index(logger=None)
        with pytest.raises(PreflightError) as exc:
            await coro
        assert exc.value.reason == "sdk_missing"
