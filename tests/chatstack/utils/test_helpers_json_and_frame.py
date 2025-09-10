# tests/test_streaming/test_helpers_json_and_frame.py
"""Unit tests for JSON/SSE helper functions in chat API routes.

Targets:
- `_dump_json(payload)`: supports pydantic v2 (`model_dump_json()`), pydantic v1
  (`.json()`), dict-like (`model_dump()`/`.dict()`), and final `json.dumps`.
- `_sse_frame(payload_json)`: wraps as `"data: {payload}\\n\\n"`.

Why:
Exercising fallback order and exact framing ensures robust serialization and SSE
compatibility across object types without touching the streaming suite.
"""

from __future__ import annotations

import json
from typing import Any

from ingenious.api.routes.chat import _dump_json, _sse_frame


class _V2OK:
    """Dummy with pydantic v2‑like `model_dump_json()`."""

    def __init__(self, payload: dict[str, Any]) -> None:
        """Store the payload to serialize."""
        self._payload = payload

    def model_dump_json(self) -> str:
        """Return a JSON string as v2 would."""
        return json.dumps(self._payload, ensure_ascii=False)


class _V1OK:
    """Dummy with pydantic v1‑like `.json()`."""

    def __init__(self, payload: dict[str, Any]) -> None:
        """Store the payload to serialize."""
        self._payload = payload

    def json(self) -> str:
        """Return a JSON string as v1 would."""
        return json.dumps(self._payload, ensure_ascii=False)


class _DictLike:
    """Dummy with dict‑like export (`model_dump` prioritized, then `.dict`)."""

    def __init__(self, payload: dict[str, Any], use_model_dump: bool = True) -> None:
        """Configure which dict-like method to expose."""
        self._payload = payload
        self._use_model_dump = use_model_dump

    def model_dump(self) -> dict[str, Any]:
        """Return the dict representation when enabled."""
        if not self._use_model_dump:
            raise AttributeError("model_dump disabled")
        return dict(self._payload)

    def dict(self) -> dict[str, Any]:  # noqa: A003 - deliberate name
        """Return the dict representation as pydantic v1 fallback."""
        return dict(self._payload)


class _RaisingString(str):
    """String subclass that raises on pydantic-like methods to hit the fallback."""

    def model_dump_json(self) -> str:
        """Simulate failure in v2 path."""
        raise ValueError("v2 fail")

    def json(self) -> str:
        """Simulate failure in v1 path."""
        raise RuntimeError("v1 fail")

    def model_dump(self) -> dict[str, Any]:
        """Simulate failure in dict-like path."""
        raise TypeError("dict-like fail")


def test_dump_json_prefers_v2_model_dump_json() -> None:
    """It prefers `model_dump_json()` when present and working."""
    obj = _V2OK({"a": 1})
    out = _dump_json(obj)
    assert out == '{"a": 1}'


def test_dump_json_falls_back_to_v1_json_when_v2_raises() -> None:
    """When v2 path raises, it falls back to `.json()`."""
    class _Both:
        def model_dump_json(self) -> str:
            raise ValueError("boom")

        def json(self) -> str:
            return json.dumps({"b": 2}, ensure_ascii=False)

    out = _dump_json(_Both())
    assert out == '{"b": 2}'


def test_dump_json_uses_model_dump_or_dict_like() -> None:
    """It serializes dict-like objects via `model_dump()`/`.dict()`."""
    obj = _DictLike({"x": "y"}, use_model_dump=True)
    assert _dump_json(obj) == '{"x": "y"}'

    obj2 = _DictLike({"k": 3}, use_model_dump=False)
    # model_dump raises → `.dict()` is used
    assert _dump_json(obj2) == '{"k": 3}'


def test_dump_json_last_resort_json_dumps_even_if_methods_raise() -> None:
    """If all preferred methods raise, it falls back to `json.dumps(payload)`."""
    # `_RaisingString` is still JSON-serializable as a string; ensures fallback path works.
    obj = _RaisingString("fallback")
    out = _dump_json(obj)
    assert out == '"fallback"'


def test_sse_frame_wraps_payload_with_prefix_and_double_newline() -> None:
    """SSE frame must be exactly 'data: {payload}\\n\\n'."""
    payload = '{"ok": true}'
    framed = _sse_frame(payload)
    assert framed == "data: {\"ok\": true}\n\n"
