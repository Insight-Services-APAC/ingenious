"""Test the fallback mechanisms for the knowledge base agent.

This module contains tests to verify that the ConversationFlow for the
knowledge base agent correctly handles failures of its primary data source
(Azure AI Search) and falls back to a secondary source (local ChromaDB).
The primary entry point is the test case that simulates a runtime error
from the Azure search provider.
"""

from __future__ import annotations

import os
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent.knowledge_base_agent import (
    ConversationFlow,
)


@pytest.mark.asyncio
async def test_kb_agent_azure_runtime_failure_falls_back_to_chroma(
    mock_ingenious_settings: MagicMock,
    tmp_path,
) -> None:
    """P0: Verify _search_knowledge_base falls back to ChromaDB when AzureSearchProvider raises a runtime exception."""

    # Minimal parent service required by IConversationFlow.__init__
    class _ParentSvc:
        """A minimal mock of the parent service needed by ConversationFlow."""

        chat_history_repository: MagicMock = MagicMock()
        openai_service: None = None  # optional; some flows may read this

        def __init__(self, cfg: NS) -> None:
            """Initialize the mock parent service with a configuration."""
            self.config = cfg
            self.conversation_flow = "knowledge_base_agent"

    # Build a minimal config that has chat_history.memory_path
    cfg: NS = NS(
        chat_history=NS(memory_path=str(tmp_path)),
        # Optional fields that might be read later:
        models=NS(),
        web=NS(streaming_chunk_size=100),
    )
    # Provide minimal Azure service so preflight runs and the provider is attempted
    cfg.azure_search_services = [NS(endpoint="https://s.net", key="sk", index_name="idx")]

    # Avoid real memory manager initialization in IConversationFlow.__init__
    flow: ConversationFlow
    with patch("ingenious.services.memory_manager.get_memory_manager", return_value=MagicMock()):
        flow = ConversationFlow(parent_multi_agent_chat_service=_ParentSvc(cfg))

    # Ensure a simple local path used by the Chroma fallback
    flow._memory_path = str(tmp_path)

    # Mock the AzureSearchProvider to fail
    mock_provider_instance: AsyncMock = AsyncMock()
    mock_provider_instance.retrieve.side_effect = RuntimeError("Azure Connection Failed")
    mock_provider_instance.close = AsyncMock()

    # Mock ChromaDB to succeed (the fallback)
    mock_chroma_client: MagicMock = MagicMock()
    mock_chroma_collection: MagicMock = MagicMock()
    mock_chroma_collection.query.return_value = {"documents": [["Fallback result from ChromaDB"]]}
    mock_chroma_client.get_collection.return_value = mock_chroma_collection

    # Minimal Azure SDK surface
    class _Cred:
        """A minimal mock for AzureKeyCredential."""

        def __init__(self, key: str) -> None:
            """Initialize the mock credential."""
            self.key = key

    class _Client:
        """A minimal mock for SearchClient."""

        def __init__(self, *, endpoint: str, index_name: str, credential: _Cred) -> None:
            """Initialize the mock search client."""
            pass

        async def get_document_count(self) -> int:
            """Return a mock document count."""
            return 1

        async def close(self) -> None:
            """Mock the async close method."""
            pass

    # Ensure local KB dir exists so local fallback path executes
    import tempfile

    temp_kb_dir = os.path.join(tempfile.gettempdir(), "knowledge_base")
    os.makedirs(temp_kb_dir, exist_ok=True)

    with (
        # --- your existing patches ---
        patch("azure.core.credentials.AzureKeyCredential", _Cred, create=True),
        patch("azure.search.documents.aio.SearchClient", _Client, create=True),
        patch(
            "ingenious.services.azure_search.provider.AzureSearchProvider",
            return_value=mock_provider_instance,
        ),
        patch("chromadb.PersistentClient", return_value=mock_chroma_client),
        patch.dict(os.environ, {"KB_POLICY": "prefer_azure"}, clear=False),
        # --- NEW: patch the KB module’s imported symbol so preflight builds our _Client ---
        patch(
            # IMPORTANT: patch the symbol where it is USED (KB module), not the factory module.
            "ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent.knowledge_base_agent.make_async_search_client",
            # We provide a small builder that adapts the KB preflight stub (SimpleNamespace)
            # into our _Client. This guarantees the preflight call `await client.get_document_count()`
            # finds the async method and succeeds in THIS test.
            new=lambda cfg: _Client(
                endpoint=getattr(cfg, "search_endpoint"),
                index_name=getattr(cfg, "search_index_name"),
                credential=_Cred(
                    # Unwrap SecretStr if the stub used it; fall back to plain str otherwise
                    getattr(cfg, "search_key").get_secret_value()
                    if hasattr(getattr(cfg, "search_key"), "get_secret_value")
                    else getattr(cfg, "search_key")
                ),
            ),
            create=True,
        ),
    ):
        # With all patches active, the KB flow will:
        # 1) pass preflight (our _Client has async get_document_count()),
        # 2) attempt Azure (calls mock_provider_instance.retrieve(...) once),
        # 3) our retrieve() raises RuntimeError(...) -> flow falls back to Chroma,
        # 4) returns Chroma results and logs the fallback,
        # 5) and your asserts on retrieve-call-count + Chroma output pass.
        result: str = await flow._search_knowledge_base(
            search_query="test query",
            use_azure_search=True,
            top_k=3,
            logger=MagicMock(),
        )

    # Azure provider was tried and failed
    mock_provider_instance.retrieve.assert_called_once_with("test query", top_k=3)
    mock_provider_instance.close.assert_called_once()

    # Fallback was used
    mock_chroma_client.get_collection.assert_called_once()
    mock_chroma_collection.query.assert_called_once()

    assert "Found relevant information from ChromaDB:" in result
    assert "Fallback result from ChromaDB" in result
