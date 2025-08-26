"""Streaming (assist) tests for KB Agent ↔ Azure AI Search integration.

This module contains two streaming tests that verify: (1) the KB agent calls the
Azure provider and honors request-level `top_k` overrides, and (2) narrated tool
JSON/chatter is filtered while real content and token counts are forwarded.

Key entry points:
- ConversationFlow.get_streaming_conversation_response (public, streaming).

I/O/deps/side effects:
- No network. Patches:
  * ConversationFlow._is_azure_search_available → True
  * ConversationFlow._preflight_azure_index_async → no-op
  * ingenious.services.azure_search.provider.AzureSearchProvider → stub provider
  * AzureClientFactory.create_openai_chat_completion_client → stub client
  * KB module aliases: AssistantAgent / FunctionTool → lightweight stubs

Usage:
- Run with `pytest -q`. Tests create temp dirs only; no persistent files.
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest

_KB_MOD_PATH: str = (
    "ingenious.services.chat_services.multi_agent.conversation_flows."
    "knowledge_base_agent.knowledge_base_agent"
)


def _make_flow(tmp_path: Any) -> Any:
    """Create a minimally initialized ConversationFlow instance for tests.

    The object is constructed via `object.__new__` to skip parent Service init,
    then attributes expected by the methods are set directly.

    Args:
        tmp_path: Pytest temporary path (used for KB/chroma locations).

    Returns:
        A ConversationFlow instance with `_config`, `_kb_path`, `_chroma_path`.
    """
    kb_mod = importlib.import_module(_KB_MOD_PATH)
    flow = object.__new__(kb_mod.ConversationFlow)

    # Minimal config expected by ConversationFlow.
    config = SimpleNamespace(
        models=[SimpleNamespace(model="gpt-4o")],
        azure_search_services=[
            SimpleNamespace(
                endpoint="https://search.example.net",
                index_name="idx",
                key="sk",  # any non-mock string suffices for availability logic
            )
        ],
        knowledge_base_mode=None,
        knowledge_base_policy=None,
    )

    flow._config = config
    flow._chat_service = None
    flow._kb_path = str(tmp_path / "kb")
    flow._chroma_path = str(tmp_path / "chroma")
    flow._last_mem_warn_ts = 0.0
    return flow


class _StubModelClient:
    """Async model client stub used by the AssistantAgent stub."""

    async def close(self) -> None:
        """Provide an awaitable close to match the real client's lifecycle."""
        return None


class _StubFunctionTool:
    """Minimal FunctionTool wrapper that stores the callable."""

    def __init__(self, fn: Any, description: str | None = None) -> None:
        """Initialize with the function and optional description."""
        self.fn = fn
        self.description = description or ""


class _StubAssistantAgent:
    """AssistantAgent stub that invokes the first tool and yields a stream.

    The stream includes:
    - a tool event (status only),
    - narrated tool JSON (should be filtered),
    - a real content chunk (should surface),
    - a usage block (to produce token_count),
    - a final TaskResult-like object (to exercise final flush).
    """

    def __init__(
        self,
        name: str,
        system_message: str,
        model_client: Any,
        tools: list[_StubFunctionTool],
        reflect_on_tool_use: bool = False,
    ) -> None:
        """Store the provided tools for later invocation in `run_stream`."""
        self._tools: list[_StubFunctionTool] = tools

    async def on_messages(self, *_: Any, **__: Any) -> Any:
        """API parity for completeness; not used in these tests."""
        return SimpleNamespace(chat_message=SimpleNamespace(content="unused"))

    async def run_stream(
        self, task: str, cancellation_token: Any
    ) -> AsyncIterator[Any]:
        """Yield a sequence of tool/status/content/usage/final objects.

        Args:
            task: The user task text (unused).
            cancellation_token: A token instance (unused in stub).

        Yields:
            Objects with shapes the ConversationFlow streamer recognizes.
        """
        # 1) Simulate a tool event.
        yield SimpleNamespace(event="tool_call")

        # 2) Call the registered search tool; its return is the assistant content.
        res: str = await self._tools[0].fn("dummy")

        # 3) Narrated tool JSON that must be filtered by the KB agent.
        yield SimpleNamespace(content='{"function_call": {"name": "search_tool"}}')

        # 4) Actual assistant content (should pass through).
        yield SimpleNamespace(content=res)

        # 5) Token usage so the agent emits a token_count chunk.
        yield SimpleNamespace(
            usage=SimpleNamespace(total_tokens=123, completion_tokens=45)
        )

        # 6) Final task result → the agent attempts a final flush.
        class _TaskResult:
            """Final task result container; class name includes 'TaskResult'."""

            def __init__(self, messages: list[Any]) -> None:
                """Store final assistant messages for the agent to flush."""
                self.messages = messages

        yield _TaskResult(messages=[SimpleNamespace(content="(tail)")])
        # End of stream.


class _SpyProvider:
    """AzureSearchProvider stub that records `retrieve` calls (query, top_k)."""

    instances: list["_SpyProvider"] = []

    def __init__(self, *_: Any, **__: Any) -> None:
        """Initialize call log and register this instance globally."""
        self.calls: list[tuple[str, int]] = []
        _SpyProvider.instances.append(self)

    async def retrieve(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """Record the call and return a minimal doc list."""
        self.calls.append((query, top_k))
        return [
            {"id": "1", "title": "doc", "snippet": "snippet", "_final_score": 0.9},
        ]

    async def close(self) -> None:
        """Provide an awaitable close for lifecycle parity."""
        return None


@pytest.mark.asyncio
async def test_streaming_assist_calls_provider_and_honors_request_topk(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure provider is called and request `kb_top_k` override is honored.

    The streaming `search_tool` resolves top_k as: request override → env → default.
    We set a request-level override and assert the provider receives that value.
    """
    kb_mod = importlib.import_module(_KB_MOD_PATH)
    flow = _make_flow(tmp_path)

    # Environment: prefer Azure; explicit request top_k override.
    monkeypatch.setenv("KB_POLICY", "prefer_azure")

    # Make Azure path available and skip real preflight.
    monkeypatch.setattr(
        kb_mod.ConversationFlow, "_is_azure_search_available", lambda _self: True
    )
    monkeypatch.setattr(
        kb_mod.ConversationFlow,
        "_preflight_azure_index_async",
        AsyncMock(return_value=None),
    )

    # Patch provider, model client, and agent/tool wrappers at the KB module site.
    with (
        patch(
            "ingenious.services.azure_search.provider.AzureSearchProvider",
            new=_SpyProvider,
        ),
        patch.object(
            kb_mod.AzureClientFactory,
            "create_openai_chat_completion_client",
            return_value=_StubModelClient(),
        ),
        patch.object(kb_mod, "AssistantAgent", new=_StubAssistantAgent),
        patch.object(kb_mod, "FunctionTool", new=_StubFunctionTool),
    ):
        from ingenious.models.chat import ChatRequest

        req = ChatRequest(user_prompt="What is X?")
        if hasattr(req, "parameters") and isinstance(req.parameters, dict):
            req.parameters["kb_top_k"] = 7
        else:
            setattr(req, "parameters", {"kb_top_k": 7})

        # Drain the streaming iterator.
        chunks: list[Any] = []
        async for ch in flow.get_streaming_conversation_response(req):
            chunks.append(ch)

    # Provider was constructed and called once with top_k == 7.
    assert _SpyProvider.instances, "Provider stub was not constructed."
    assert _SpyProvider.instances[0].calls, "Provider.retrieve was not called."
    _, seen_top_k = _SpyProvider.instances[0].calls[0]
    assert seen_top_k == 7, f"expected top_k=7, got {seen_top_k}"

    # Sanity: the stream included token_count and at least one content chunk.
    assert any(getattr(c, "chunk_type", "") == "token_count" for c in chunks)
    assert any(
        getattr(c, "chunk_type", "") == "content" and getattr(c, "content", "")
        for c in chunks
    )


@pytest.mark.asyncio
async def test_streaming_filters_tool_chatter_and_surfaces_final_content(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify tool chatter is filtered and final content/usage are surfaced.

    Streaming tools may yield internal JSON/narration. The agent should drop
    that chatter while passing substantive content and token counts.
    """
    kb_mod = importlib.import_module(_KB_MOD_PATH)
    flow = _make_flow(tmp_path)

    # Make Azure path available and skip real preflight.
    monkeypatch.setattr(
        kb_mod.ConversationFlow, "_is_azure_search_available", lambda _self: True
    )
    monkeypatch.setattr(
        kb_mod.ConversationFlow,
        "_preflight_azure_index_async",
        AsyncMock(return_value=None),
    )

    with (
        patch(
            "ingenious.services.azure_search.provider.AzureSearchProvider",
            new=_SpyProvider,
        ),
        patch.object(
            kb_mod.AzureClientFactory,
            "create_openai_chat_completion_client",
            return_value=_StubModelClient(),
        ),
        patch.object(kb_mod, "AssistantAgent", new=_StubAssistantAgent),
        patch.object(kb_mod, "FunctionTool", new=_StubFunctionTool),
    ):
        from ingenious.models.chat import ChatRequest

        req = ChatRequest(user_prompt="How to foo?")
        if hasattr(req, "parameters") and isinstance(req.parameters, dict):
            req.parameters["kb_top_k"] = 3

        chunks: list[Any] = []
        async for ch in flow.get_streaming_conversation_response(req):
            chunks.append(ch)

    # Join surfaced content.
    surfaced_texts: list[str] = [
        getattr(c, "content", "")
        for c in chunks
        if getattr(c, "chunk_type", "") == "content"
    ]
    joined: str = " ".join(surfaced_texts)

    # Assertions: tool JSON filtered; answer body present; token_count emitted.
    assert "function_call" not in joined and "search_tool(" not in joined
    assert "doc" in joined or "snippet" in joined
    assert any(getattr(c, "chunk_type", "") == "token_count" for c in chunks)
