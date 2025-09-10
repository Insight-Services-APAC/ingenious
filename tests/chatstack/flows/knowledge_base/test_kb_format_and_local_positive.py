from __future__ import annotations

"""KB formatting + local Chroma positive retrieval tests.

Why:
    Close gaps around:
    - Azure results formatting and snippet/content truncation.
    - Local Chroma *positive* retrieval (previous tests focused on negatives).

Usage:
    `pytest -q tests/test_additional/test_kb_format_and_local_positive.py`
"""

import os
import sys
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent.knowledge_base_agent import (  # noqa: E501
    ConversationFlow as KBFlow,
)

TITLE: str = "Title"
SCORE: float = 0.9
LONG_SNIPPET: str = "x" * 50
LONG_CONTENT: str = "y" * 50
KB_FILE_NAME: str = "a.txt"
CHROMA_COLLECTION: str = "knowledge_base"


def _new_kb_flow_uninitialized() -> KBFlow:
    """Construct a KB flow instance without running __init__.

    Intent:
        Avoid base-class side effects (memory manager init) since we only need
        specific helper methods in these focused unit tests.
    """
    return object.__new__(KBFlow)  # type: ignore[no-any-return]


def _assign_local_paths(flow: KBFlow, kb_dir: str, chroma_dir: str) -> None:
    """Assign local paths needed for _search_local_chroma.

    Args:
        flow: Flow instance (uninitialized).
        kb_dir: Knowledge base directory path.
        chroma_dir: Chroma persistence directory.
    """
    flow._kb_path = kb_dir  # type: ignore[attr-defined]
    flow._chroma_path = chroma_dir  # type: ignore[attr-defined]
    # Minimal config stub so helpers that reference _config don't crash
    flow._config = SimpleNamespace()  # type: ignore[attr-defined]


def _install_fake_chromadb(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install a tiny fake 'chromadb' module into sys.modules.

    Why:
        Allows exercising the positive path without external dependency.
    """

    class _FakeCollection:
        def add(self, documents: List[str], ids: List[str]) -> None:
            """Accept added documents for seeding."""
            assert documents and ids

        def query(
            self, query_texts: List[str], n_results: int
        ) -> Dict[str, List[List[str]]]:
            """Return one hit to trigger the positive path."""
            return {"documents": [["hit-from-stub"]]}

    class _FakeClient:
        def __init__(self, path: str) -> None:
            self.path = path

        def get_collection(self, name: str) -> _FakeCollection:
            raise RuntimeError("no collection yet")

        def create_collection(self, name: str) -> _FakeCollection:
            assert name == CHROMA_COLLECTION
            return _FakeCollection()

    fake_mod = SimpleNamespace(PersistentClient=_FakeClient)
    monkeypatch.setitem(sys.modules, "chromadb", fake_mod)


def test_kb_azure_results_formatting_and_snippet_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify snippet/content truncation and formatted Azure output.

    Intent:
        `_format_azure_results` should:
        - Start with the Azure header line.
        - Include an item header `"[1] Title (score=...)"`.
        - Honor `KB_AZURE_SNIPPET_CAP` to truncate snippet/content.
    """
    CAP: int = 10
    monkeypatch.setenv("KB_AZURE_SNIPPET_CAP", str(CAP))

    flow = _new_kb_flow_uninitialized()
    chunks: List[Dict[str, Any]] = [
        {"title": TITLE, "_final_score": SCORE, "snippet": LONG_SNIPPET, "content": LONG_CONTENT}
    ]

    out = flow._format_azure_results(chunks)  # type: ignore[attr-defined]
    assert out.startswith("Found relevant information from Azure AI Search:")
    assert "[1] Title (score=" in out
    assert LONG_SNIPPET not in out  # truncated
    assert LONG_CONTENT not in out  # truncated


@pytest.mark.asyncio
async def test_kb_local_chroma_positive_retrieval(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """Exercise the positive local Chroma path using a stubbed module.

    Intent:
        Ensure `_search_local_chroma` returns the success prefix when
        documents exist and the Chroma client returns hits.
    """
    _install_fake_chromadb(monkeypatch)

    kb_dir = tmp_path / "kb"
    chroma_dir = tmp_path / "chroma"
    kb_dir.mkdir()
    (kb_dir / KB_FILE_NAME).write_text("alpha\n\nbeta", encoding="utf-8")

    flow = _new_kb_flow_uninitialized()
    _assign_local_paths(flow, str(kb_dir), str(chroma_dir))

    out = await flow._search_local_chroma(  # type: ignore[attr-defined]
        search_query="alpha", top_k=3, logger=None
    )
    assert out.startswith("Found relevant information from ChromaDB:")
