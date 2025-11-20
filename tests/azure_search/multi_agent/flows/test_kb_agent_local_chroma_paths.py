"""Test the local ChromaDB knowledge base search functionality.

This module contains tests for the `_search_local_chroma` method within the
Knowledge Base Agent's conversation flow. It verifies several key behaviors
related to the local vector database search feature, which relies on the
optional `chromadb` package.

The tests cover:
- Graceful failure when the `chromadb` library is not installed.
- Correct document ingestion, chunking, and querying on a successful path.
- Proper error handling when the underlying database query fails.
"""

from __future__ import annotations

import builtins
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pytest import MonkeyPatch

import ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent.knowledge_base_agent as kb


@pytest.mark.asyncio
async def test_chromadb_import_error_returns_install_hint(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Verify that a ModuleNotFoundError for chromadb returns an install hint."""
    # Ensure KB dir exists so we hit the import branch (not the empty-dir early return)
    kb_dir = tmp_path / "knowledge_base"
    kb_dir.mkdir()

    # Force "import chromadb" to raise ModuleNotFoundError
    original_import: Any = builtins.__import__

    def bad_import(name: str, *a: Any, **k: Any) -> types.ModuleType:
        """Raise ModuleNotFoundError if the import is for 'chromadb'."""
        if name == "chromadb":
            raise ModuleNotFoundError("no chromadb")
        return original_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", bad_import)

    flow: kb.ConversationFlow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    flow._config = SimpleNamespace(models=[SimpleNamespace(model="gpt-5")])
    flow._chat_service: Any = None
    flow._memory_path = str(tmp_path)
    flow._kb_path = str(kb_dir)
    flow._chroma_path = str(tmp_path / "chroma_db")

    out: str = await flow._search_local_chroma("q", top_k=2, logger=None)
    assert out.startswith("Error: ChromaDB not installed")


@pytest.mark.asyncio
async def test_local_ingest_chunking_and_ids_and_query_success(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Test successful ingestion, chunking, ID generation, and querying."""
    # Build KB files with blank-line chunking and ignored extensions
    kb_path = tmp_path / "knowledge_base"
    kb_path.mkdir()
    (kb_path / "a.md").write_text("A1\n\nA2\n\nA3")
    (kb_path / "b.txt").write_text("B1\n\nB2")
    (kb_path / "c.pdf").write_text("IGNORED")  # ignored

    # Stub chromadb client/collection
    chroma = types.ModuleType("chromadb")
    added_payload: dict[str, list[str]] = {}

    class _Coll:
        """A mock ChromaDB collection for testing."""

        def add(self, documents: list[str], ids: list[str]) -> None:
            """Capture documents and IDs that are added."""
            added_payload["documents"] = documents
            added_payload["ids"] = ids

        def query(self, query_texts: list[str], n_results: int) -> dict[str, list[list[str]]]:
            """Return a canned query result."""
            return {"documents": [["Match1", "Match2"]]}

    class _Cli:
        """A mock ChromaDB PersistentClient for testing."""

        def __init__(self, path: str) -> None:
            """Store the database path."""
            self.path: str = path

        def get_collection(self, name: str) -> _Coll:
            """Simulate getting a non-existent collection to trigger creation."""
            raise Exception("no existing")

        def create_collection(self, name: str) -> _Coll:
            """Return a new mock collection."""
            return _Coll()

    chroma.PersistentClient = _Cli  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "chromadb", chroma)

    flow: kb.ConversationFlow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    flow._config = SimpleNamespace(models=[SimpleNamespace(model="gpt-5")])
    flow._chat_service: Any = None
    flow._memory_path = str(tmp_path)
    flow._kb_path = str(kb_path)
    flow._chroma_path = str(tmp_path / "chroma_db")

    out: str = await flow._search_local_chroma("alpha", top_k=3, logger=None)
    assert "Found relevant information from ChromaDB:" in out

    # Documents and ids were ingested with chunk suffixes
    docs: list[str] = added_payload["documents"]
    ids: list[str] = added_payload["ids"]
    # Expect 5 chunks: 3 from a.md, 2 from b.txt
    assert len(docs) == 5
    assert set(ids) == {
        "a.md_chunk_0",
        "a.md_chunk_1",
        "a.md_chunk_2",
        "b.txt_chunk_0",
        "b.txt_chunk_1",
    }
    assert "A1" in " ".join(docs) and "B2" in " ".join(docs)


@pytest.mark.asyncio
async def test_local_query_failure_returns_search_error(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Verify that a query failure is caught and returns a search error message."""
    kb_path: Path = tmp_path / "knowledge_base"
    kb_path.mkdir()

    chroma = types.ModuleType("chromadb")

    class _Coll:
        """A mock ChromaDB collection that fails on query."""

        def add(self, documents: list[str], ids: list[str]) -> None:
            """Do nothing for the add operation."""
            pass

        def query(self, *a: Any, **k: Any) -> Any:
            """Raise an exception to simulate a query failure."""
            raise RuntimeError("bad query")

    class _Cli:
        """A mock ChromaDB PersistentClient for testing query failures."""

        def __init__(self, path: str) -> None:
            """Store the database path."""
            self.path: str = path

        def get_collection(self, name: str) -> _Coll:
            """Return the mock collection."""
            return _Coll()

        def create_collection(self, name: str) -> _Coll:
            """Return the mock collection."""
            return _Coll()

    chroma.PersistentClient = _Cli  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "chromadb", chroma)

    flow: kb.ConversationFlow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    flow._config = SimpleNamespace(models=[SimpleNamespace(model="gpt-5")])
    flow._chat_service: Any = None
    flow._memory_path = str(tmp_path)
    flow._kb_path = str(kb_path)
    flow._chroma_path = str(tmp_path / "chroma_db")

    out: str = await flow._search_local_chroma("q", top_k=2, logger=None)
    assert out.startswith("Search error:")
