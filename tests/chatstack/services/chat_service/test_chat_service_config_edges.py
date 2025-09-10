# tests/test_streaming/test_chat_service_config_edges.py
"""ChatService configuration edge-case tests (non-streaming chunk size).

Target:
- `ChatService._get_streaming_chunk_size()` should correctly interpret values
  from both object-style and dict-style `config.web`, handle numeric strings,
  and fall back to the default when missing/invalid.

Why:
This supplements streaming tests by focusing on the private chunk-size resolver
without re-testing streaming behavior.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from ingenious.services.chat_service import (
    DEFAULT_STREAMING_CHUNK_SIZE,
    ChatService,
)


class _TinyBackend:
    """Minimal backend satisfying import expectations."""

    def __init__(
        self, config: Any, chat_history_repository: Any, conversation_flow: str
    ) -> None:
        """Store inputs; backend methods are not used here."""
        self._cfg = config
        self._repo = chat_history_repository
        self._flow = conversation_flow

    async def get_chat_response(self, *_args: Any, **_kwargs: Any) -> Any:
        """Not used in these tests (stub for interface completeness)."""
        raise AssertionError("get_chat_response should not be called in this test")


def _make_service(monkeypatch: pytest.MonkeyPatch, config: Any) -> ChatService:
    """Construct ChatService with a fake backend importer."""
    import ingenious.services.chat_service as svc_mod

    monkeypatch.setattr(
        "ingenious.utils.imports.import_class_with_fallback", lambda *a, **k: _TinyBackend
    )
    return ChatService(
        chat_service_type="tiny",
        chat_history_repository=object(),
        conversation_flow="noop",
        config=config,
    )


def test_chunk_size_object_web(monkeypatch: pytest.MonkeyPatch) -> None:
    """Object-style `config.web.streaming_chunk_size=25` → returns 25."""
    config = SimpleNamespace(web=SimpleNamespace(streaming_chunk_size=25))
    cs = _make_service(monkeypatch, config)
    assert cs._get_streaming_chunk_size() == 25


def test_chunk_size_dict_web_numeric_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dict-style `{'streaming_chunk_size': '64'}` → coerced to int 64."""
    config = SimpleNamespace(web={"streaming_chunk_size": "64"})
    cs = _make_service(monkeypatch, config)
    assert cs._get_streaming_chunk_size() == 64


def test_chunk_size_missing_or_invalid_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing/invalid/negative values → DEFAULT_STREAMING_CHUNK_SIZE (100)."""
    # Missing web entirely
    cfg_missing = SimpleNamespace()
    assert _make_service(monkeypatch, cfg_missing)._get_streaming_chunk_size() == DEFAULT_STREAMING_CHUNK_SIZE

    # Negative number
    cfg_neg = SimpleNamespace(web=SimpleNamespace(streaming_chunk_size=-5))
    assert _make_service(monkeypatch, cfg_neg)._get_streaming_chunk_size() == DEFAULT_STREAMING_CHUNK_SIZE

    # Non-numeric string in dict
    cfg_str = SimpleNamespace(web={"streaming_chunk_size": "abc"})
    assert _make_service(monkeypatch, cfg_str)._get_streaming_chunk_size() == DEFAULT_STREAMING_CHUNK_SIZE
