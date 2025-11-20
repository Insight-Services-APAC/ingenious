"""Tests for the Knowledge Base (KB) agent conversation flow.

This module contains unit and integration tests for the ConversationFlow
implemented in `ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent.knowledge_base_agent`.

It verifies the core logic of the KB agent, including:
- Correctly routing requests to Azure AI Search or a local ChromaDB fallback.
- Handling of various configurations via environment variables (e.g., KB_MODE, KB_TOPK_*).
- Prioritizing request-level parameters over environment variables.
- Graceful failure handling and policy enforcement (e.g., `prefer_azure`).
- Correct formatting of search results in the final agent response.

The tests use extensive patching and test doubles to isolate the agent from
live services and external dependencies.
"""

from __future__ import annotations

import logging
import os
import sys
import types
from types import SimpleNamespace
from typing import Any, Callable, Coroutine, Dict, Iterator, List, Optional, cast

import pytest

# Import the module under test (KB Agent)
import ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent.knowledge_base_agent as kb

# ──────────────────────────────────────────────────────────────────────────────
# Test doubles / small helpers
# ──────────────────────────────────────────────────────────────────────────────


class AcceptingLogHandler(logging.Handler):
    """A logging handler that accepts arbitrary kwargs in __init__ (mimics tracker)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the handler, accepting and ignoring any arguments."""
        super().__init__()

    def emit(self, record: logging.LogRecord) -> None:
        """Handle a log record. This implementation does nothing."""
        pass


class DummyLLMClient:
    """A minimal stub for an LLM client, providing an async `close` method."""

    async def close(self) -> None:
        """Simulate closing the client connection."""
        pass


class DummyFunctionTool:
    """Mimics a tool wrapper; stores a callable and forwards calls."""

    def __init__(
        self, func: Callable[..., Coroutine[Any, Any, Any]], description: str = ""
    ) -> None:
        """Initialize the tool with a function to execute.

        Args:
            func: The asynchronous callable that this tool will wrap.
            description: An optional description of the tool's purpose.
        """
        self.function = func
        self.description = description

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the wrapped function when the tool instance is called."""
        return await self.function(*args, **kwargs)

    # Some frameworks call invoke(), keep it for safety
    async def invoke(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the wrapped function via an `invoke` method for compatibility."""
        return await self.function(*args, **kwargs)


class DummyAssistantAgent:
    """Very small assistant that just calls the first tool with a search query."""

    def __init__(
        self,
        name: str,
        system_message: str,
        model_client: Any,
        tools: list[DummyFunctionTool],
        reflect_on_tool_use: bool = True,
    ) -> None:
        """Initialize the dummy agent.

        Args:
            name: The name of the agent.
            system_message: The system prompt for the agent.
            model_client: A dummy model client.
            tools: A list of tools available to the agent.
            reflect_on_tool_use: A flag for reflection (unused in this dummy).
        """
        self._name = name
        self._system_message = system_message
        self._client = model_client
        self._tools = tools

    async def on_messages(self, messages: list[Any], cancellation_token: Any | None = None) -> Any:
        """Simulate processing messages by calling the first available tool.

        It parses the user question from the message content and passes it
        as the primary argument to the first tool's function.

        Args:
            messages: A list of incoming messages.
            cancellation_token: An optional token for cancellation.

        Returns:
            A dummy response object containing the tool's output.
        """
        # Pull the question text from the message content.
        content = getattr(messages[0], "content", "")
        # The agent sends "Context: ...\n\nUser question: <q>"
        if "User question:" in content:
            q = content.split("User question:", 1)[1].strip()
        else:
            q = content.strip()

        # Use the first tool with the parsed query
        data = await self._tools[0].function(q)  # our DummyFunctionTool keeps the original callable

        class _Msg:
            def __init__(self, c: Any) -> None:
                self.content = c

        class _Resp:
            def __init__(self, c: Any) -> None:
                self.chat_message = _Msg(c)

        return _Resp(data)

    # Not used by these tests, but kept for completeness
    def run_stream(
        self, task: str, cancellation_token: Any | None = None
    ) -> Coroutine[Any, Any, Any]:
        """Simulate a streaming response generator (unused in these tests)."""

        async def _gen() -> Any:
            class _Msg:
                def __init__(self, c: str) -> None:
                    self.content = c

            yield _Msg("stream content")

        return _gen()


def install_minimal_autogen(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide tiny autogen_core, autogen_core.tools, autogen_agentchat.messages modules.

    This function patches `sys.modules` to inject fake `autogen` modules,
    avoiding the need for a full installation while satisfying the module's imports.
    """
    core_mod = types.ModuleType("autogen_core")
    core_mod.EVENT_LOGGER_NAME = "autogen"

    class _CT:
        pass

    core_mod.CancellationToken = _CT
    monkeypatch.setitem(sys.modules, "autogen_core", core_mod)

    tools_mod = types.ModuleType("autogen_core.tools")

    class _FT:
        pass

    tools_mod.FunctionTool = _FT
    monkeypatch.setitem(sys.modules, "autogen_core.tools", tools_mod)

    agents_mod = types.ModuleType("autogen_agentchat.agents")

    class _Assistant:
        pass

    agents_mod.AssistantAgent = _Assistant
    monkeypatch.setitem(sys.modules, "autogen_agentchat.agents", agents_mod)

    msgs_mod = types.ModuleType("autogen_agentchat.messages")

    class TextMessage:
        def __init__(self, content: str, source: str) -> None:
            self.content = content
            self.source = source

    msgs_mod.TextMessage = TextMessage
    monkeypatch.setitem(sys.modules, "autogen_agentchat.messages", msgs_mod)


def install_dummy_token_counter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install a dummy token counter that always returns zero.

    This patches `sys.modules` to replace the real token counter utility,
    preventing it from running and simplifying test setup.
    """
    tc = types.ModuleType("ingenious.utils.token_counter")

    def _num_tokens_from_messages(msgs: Any, model: Any) -> int:
        return 0

    tc.num_tokens_from_messages = _num_tokens_from_messages
    monkeypatch.setitem(sys.modules, "ingenious.utils.token_counter", tc)


def install_memory_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install a stub memory manager with no-op methods.

    This patches `sys.modules` to replace the real memory manager, isolating
    tests from chat history and memory side effects.
    """
    mm = types.ModuleType("ingenious.services.memory_manager")

    class _MM:
        async def close(self) -> None:
            pass

        async def maintain_memory(self, new_content: str, max_words: int) -> None:
            return None

    def get_memory_manager(config: Any, path: str) -> _MM:
        return _MM()

    async def run_async_memory_operation(coro: Coroutine[Any, Any, Any]) -> Any:
        return await coro

    mm.get_memory_manager = get_memory_manager
    mm.run_async_memory_operation = run_async_memory_operation
    monkeypatch.setitem(sys.modules, "ingenious.services.memory_manager", mm)


def install_fake_provider(
    monkeypatch: pytest.MonkeyPatch,
    results: list[dict[str, Any]] | None = None,
    raise_exc: Exception | None = None,
) -> list[dict[str, Any]]:
    """Install a fake AzureSearchProvider that records calls and optionally raises.

    This function patches `sys.modules` to replace the real Azure Search provider
    with a test double. This allows tests to inspect calls made to the provider,
    control its return values, and simulate failure scenarios.

    Args:
        monkeypatch: The pytest monkeypatch fixture.
        results: A list of document dictionaries to return from `retrieve`.
        raise_exc: An exception to raise when `retrieve` is called.

    Returns:
        A list that will be populated with call arguments for inspection.
    """
    prov_mod = types.ModuleType("ingenious.services.azure_search.provider")
    calls: List[Dict[str, Any]] = []

    class AzureSearchProvider:
        def __init__(self, settings: Any, enable_answer_generation: bool | None = None) -> None:
            pass

        async def retrieve(
            self, query: str, top_k: int = 10, **kwargs: Any
        ) -> list[dict[str, Any]]:
            calls.append({"query": query, "top_k": top_k, "kwargs": kwargs})
            if raise_exc:
                raise raise_exc
            return results or []

        async def answer(self, query: str) -> dict[str, Any]:
            return {"answer": "stub", "source_chunks": []}

        async def close(self) -> None:
            pass

    prov_mod.AzureSearchProvider = AzureSearchProvider
    monkeypatch.setitem(sys.modules, "ingenious.services.azure_search.provider", prov_mod)
    return calls


def install_fake_chromadb(
    monkeypatch: pytest.MonkeyPatch, documents: Optional[List[str]] = None
) -> None:
    """Stub chromadb to return canned documents (so fallback path is deterministic).

    This patches `sys.modules` to replace the `chromadb` library with a minimal
    fake implementation, allowing tests to verify the fallback logic without a
    real ChromaDB instance.
    """
    chroma_mod = types.ModuleType("chromadb")

    class _Collection:
        def add(self, documents: list[str], ids: list[str]) -> None:
            pass

        def query(self, query_texts: list[str], n_results: int) -> dict[str, list[list[str]]]:
            docs = documents or ["Chroma Fallback Doc"]
            return {"documents": [docs[:n_results]]}

    class _Client:
        def __init__(self, path: str) -> None:
            self._path = path

        def get_collection(self, name: str) -> _Collection:
            return _Collection()

        def create_collection(self, name: str) -> _Collection:
            return _Collection()

    chroma_mod.PersistentClient = _Client
    monkeypatch.setitem(sys.modules, "chromadb", chroma_mod)


@pytest.fixture
def azure_sdk_compat(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide a fully-compatible, in-process fake Azure SDK *and*.

    ensure the KB module builds its SearchClient from that fake.

    Why we do this:
    ---------------
    - The KB agent's preflight calls `await client.get_document_count()`.
    - We don't want real cloud calls or the real SDK in tests.
    - So we:
      1) publish tiny fake `azure.*` modules into `sys.modules` so imports resolve;
      2) patch the *KB module's* `make_async_search_client` to instantiate *our* fake
         async `SearchClient`, guaranteeing it has the async methods the preflight calls.

    Without step (2), some other fake (lacking `get_document_count`) can still be
    returned by previous patches in the suite, causing the observed AttributeError.
    """
    import sys
    import types

    # -----------------------------
    # 1) Define minimal fake SDK
    # -----------------------------

    class _FakeAzureKeyCredential:
        """Fake stand-in for azure.core.credentials.AzureKeyCredential.

        It simply stores the key; no real auth is performed.
        """

        def __init__(self, key: str) -> None:
            self.key = key

    class _FakeAsyncSearchClient:
        """Fake stand-in for azure.search.documents.aio.SearchClient that implements.

        exactly the async methods our KB preflight uses:
          - get_document_count (async)
          - close (async)
        """

        def __init__(self, *, endpoint: str, index_name: str, credential: Any) -> None:
            self.endpoint = endpoint
            self.index_name = index_name
            self.credential = credential
            self._closed = False

        async def get_document_count(self) -> int:
            """Return a deterministic positive value so preflight "succeeds".

            If you need to simulate a failing preflight in some tests, modify
            this to raise an exception (e.g., RuntimeError("401 Unauthorized")).
            """
            return 1

        async def close(self) -> None:
            """Simulate closing the client asynchronously."""
            self._closed = True

    # ---------------------------------------------------
    # 2) Publish fake azure.* modules into sys.modules
    #    so `from azure... import ...` resolves to these.
    # ---------------------------------------------------

    fake_credentials_mod = types.ModuleType("azure.core.credentials")
    setattr(fake_credentials_mod, "AzureKeyCredential", _FakeAzureKeyCredential)
    monkeypatch.setitem(sys.modules, "azure.core.credentials", fake_credentials_mod)

    fake_aio_mod = types.ModuleType("azure.search.documents.aio")
    setattr(fake_aio_mod, "SearchClient", _FakeAsyncSearchClient)
    monkeypatch.setitem(sys.modules, "azure.search.documents.aio", fake_aio_mod)

    # -----------------------------------------------------------------
    # 3) Patch the *KB module's* make_async_search_client symbol so that the
    #    KB preflight *always* constructs our fake async client above.
    #
    #    IMPORTANT: We patch the symbol where it is USED (the KB module),
    #    not the factory module, because the KB file imported the symbol
    #    by value:
    #       from ingenious.services.azure_search.client_init import make_async_search_client
    # -----------------------------------------------------------------

    # Import the module-under-test alias already used at top of file
    # (it’s the same as: import ... as kb; we reuse that here)
    # If you don’t have `kb` in this scope, do the explicit import:
    # import ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent.knowledge_base_agent as kb

    def _build_fake_client_from_cfg(cfg: Any) -> _FakeAsyncSearchClient:
        """The KB preflight passes a SimpleNamespace-like stub carrying attributes.

          - search_endpoint
          - search_index_name
          - search_key (either a plain str or a SecretStr)
        We unwrap SecretStr if present and return our fake client.
        """
        endpoint = getattr(cfg, "search_endpoint")
        index_name = getattr(cfg, "search_index_name")

        # Unwrap optional SecretStr (tests might pass a plain string instead).
        key_obj = getattr(cfg, "search_key", "")
        if hasattr(key_obj, "get_secret_value"):
            try:
                key = key_obj.get_secret_value()
            except Exception:
                key = ""
        else:
            key = key_obj or ""

        return _FakeAsyncSearchClient(
            endpoint=endpoint,
            index_name=index_name,
            credential=_FakeAzureKeyCredential(key),
        )

    # Patch the KB module's symbol so preflight always gets our fake with the right surface.
    monkeypatch.setattr(kb, "make_async_search_client", _build_fake_client_from_cfg, raising=True)

    # -----------------------------------------------------------------
    # 4) (Optional) Reset any cached factory singleton to avoid stale
    #    state if other tests touched it in a different order.
    #    This is defensive; ignore if the symbol isn't present.
    # -----------------------------------------------------------------
    try:
        monkeypatch.setattr(
            "ingenious.services.azure_search.client_init._FACTORY_SINGLETON",
            None,
            raising=False,
        )
    except Exception:
        pass


def make_config(
    memory_path: str,
    *,
    endpoint: str = "https://example.search.windows.net",
    key: str = "real-key",
    index_name: str = "idx",
) -> SimpleNamespace:
    """Create a very small config object with just the fields the KB flow reads.

    This helper simplifies test setup by constructing a `SimpleNamespace` object
    that mimics the structure of the application's main configuration, but
    only includes the attributes relevant to the knowledge base agent.
    """
    chat_history = SimpleNamespace(memory_path=memory_path)
    # Only 'model' field is read by token counter
    models = [SimpleNamespace(model="gpt-5")]
    azure_service = SimpleNamespace(
        endpoint=endpoint,
        key=key,
        index_name=index_name,
        use_semantic_ranking=False,
        semantic_ranking=False,
        semantic_configuration=None,
        top_k_retrieval=20,
        top_n_final=5,
        id_field="id",
        content_field="content",
        vector_field="vector",
    )
    # The flow also accesses some unrelated fields on config, but we can keep them absent.
    cfg = SimpleNamespace(
        chat_history=chat_history,
        models=models,
        azure_search_services=[azure_service],
        # The KB flow references _chat_service.chat_history_repository sometimes;
        # we will build the parent service below with this repository.
    )
    return cfg


class DummyChatHistoryRepo:
    """A test double for the chat history repository."""

    async def get_thread_messages(self, thread_id: str) -> list[Any]:
        """Return an empty list of messages to prevent memory context from affecting tests."""
        # Return empty list so memory context is blank and doesn't affect assertions
        return []


class DummyParentService:
    """A test double for the parent service that holds config and repositories."""

    def __init__(self, config: SimpleNamespace) -> None:
        """Initialize the service with config and a dummy chat history repo."""
        self.config = config
        self.chat_history_repository = DummyChatHistoryRepo()


# ──────────────────────────────────────────────────────────────────────────────
# Autouse fixture: safe patching for every test in THIS FILE
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _common_patches(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Run automatically for every test in this module.

    This fixture provides minimal stubs for external dependencies like autogen,
    the token counter, and the memory manager. It also patches symbols within
    the knowledge base agent module itself to replace them with test doubles,
    ensuring an isolated and predictable test environment.
    """
    install_minimal_autogen(monkeypatch)
    install_dummy_token_counter(monkeypatch)
    install_memory_manager(monkeypatch)

    # Patch new client factory
    monkeypatch.setattr(
        kb,
        "AzureClientFactory",
        SimpleNamespace(create_openai_chat_completion_client=lambda _cfg: DummyLLMClient()),
    )
    monkeypatch.setattr(kb, "LLMUsageTracker", AcceptingLogHandler, raising=False)
    monkeypatch.setattr(kb, "FunctionTool", DummyFunctionTool)
    monkeypatch.setattr(kb, "AssistantAgent", DummyAssistantAgent)

    # Clean up any env that could influence tests
    for var in (
        "KB_MODE",
        "KB_TOPK_DIRECT",
        "KB_TOPK_ASSIST",
        "AZURE_SEARCH_DEFAULT_INDEX",
        "KB_POLICY",
    ):
        monkeypatch.delenv(var, raising=False)

    yield


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_kb_agent_uses_azure_search_when_configured(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, azure_sdk_compat: None
) -> None:
    """Verify the agent uses Azure Search by default with the correct top_k."""
    calls = install_fake_provider(
        monkeypatch,
        results=[{"id": "1", "title": "T", "snippet": "S", "content": "Alpha"}],
    )

    cfg = make_config(str(tmp_path))
    flow = kb.ConversationFlow(DummyParentService(cfg))

    req = kb.ChatRequest(user_prompt="q")
    resp = await flow.get_conversation_response(req)

    assert "Found relevant information from Azure AI Search" in resp.agent_response
    # Direct mode default → top_k=3
    assert len(calls) == 1
    assert calls[0]["top_k"] == 3


@pytest.mark.asyncio
async def test_kb_agent_assist_mode_topk_5(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, azure_sdk_compat: None
) -> None:
    """Verify that 'assist' mode changes the default top_k to 5."""
    os.environ["KB_MODE"] = "assist"

    calls = install_fake_provider(
        monkeypatch,
        results=[{"id": "1", "title": "T", "snippet": "S", "content": "Alpha"}],
    )

    cfg = make_config(str(tmp_path))
    flow = kb.ConversationFlow(DummyParentService(cfg))

    req = kb.ChatRequest(user_prompt="q")
    resp = await flow.get_conversation_response(req)

    assert "Found relevant information from Azure AI Search" in resp.agent_response
    assert len(calls) == 1
    # Assist mode default → top_k=5
    assert calls[0]["top_k"] == 5


@pytest.mark.asyncio
async def test_kb_agent_default_index_from_env_when_missing(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    azure_sdk_compat: None,
) -> None:
    """Verify the agent uses AZURE_SEARCH_DEFAULT_INDEX when the config lacks an index."""
    # Service has no index configured
    cfg = make_config(str(tmp_path), index_name="")
    # Env supplies default index
    os.environ["AZURE_SEARCH_DEFAULT_INDEX"] = "docs"

    calls = install_fake_provider(
        monkeypatch,
        results=[{"id": "1", "title": "Doc", "snippet": "Info", "content": "Alpha"}],
    )

    flow = kb.ConversationFlow(DummyParentService(cfg))
    caplog.set_level(logging.INFO)

    resp = await flow.get_conversation_response(kb.ChatRequest(user_prompt="q"))

    assert "Found relevant information from Azure AI Search" in resp.agent_response
    assert len(calls) == 1  # provider was used (no fallback)
    # No WARNING about empty KB directory or missing index (INFO is acceptable)
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert not any("Knowledge base directory is empty" in (r.getMessage() or "") for r in warnings)
    assert not any("using fallback default" in (r.getMessage() or "") for r in warnings)


@pytest.mark.asyncio
async def test_kb_agent_azure_failure_falls_back_to_chroma_with_message(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, azure_sdk_compat: None
) -> None:
    """Verify that Azure Search failures trigger a fallback to ChromaDB when policy allows."""
    # Azure provider is importable but fails at runtime
    calls = install_fake_provider(monkeypatch, raise_exc=RuntimeError("503 Service Unavailable"))
    install_fake_chromadb(monkeypatch, documents=["C1", "C2"])

    cfg = make_config(str(tmp_path))
    flow = kb.ConversationFlow(DummyParentService(cfg))

    # Allow fallback when Azure fails (default policy is azure_only)
    os.environ["KB_POLICY"] = "prefer_azure"
    # Ensure the local KB directory exists so Chroma path is taken instead of "empty dir"
    os.makedirs(os.path.join(str(tmp_path), "knowledge_base"), exist_ok=True)

    resp = await flow.get_conversation_response(kb.ChatRequest(user_prompt="alpha?"))

    assert "Found relevant information from ChromaDB" in resp.agent_response
    # Provider was attempted once
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_kb_agent_maps_titles_and_snippets_in_output(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, azure_sdk_compat: None
) -> None:
    """Verify search results are correctly formatted with title, snippet, and content."""
    calls = install_fake_provider(
        monkeypatch,
        results=[{"id": "1", "title": "T", "snippet": "S", "content": "Alpha"}],
    )

    cfg = make_config(str(tmp_path))
    flow = kb.ConversationFlow(DummyParentService(cfg))

    resp = await flow.get_conversation_response(kb.ChatRequest(user_prompt="q"))
    out = resp.agent_response

    assert "Found relevant information from Azure AI Search" in out
    assert "[1] T (score=" in out  # allow blank score
    assert "S" in out  # snippet included
    # content is also preserved (agent now includes both snippet and content)
    assert "Alpha" in out

    assert len(calls) == 1
    assert calls[0]["top_k"] == 3


@pytest.mark.asyncio
async def test_kb_agent_request_override_topk_wins(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, azure_sdk_compat: None
) -> None:
    """Verify that a per-request `kb_top_k` parameter overrides all defaults."""
    calls = install_fake_provider(
        monkeypatch,
        results=[{"id": "1", "title": "T", "snippet": "S", "content": "X"}],
    )

    cfg = make_config(str(tmp_path))
    flow = kb.ConversationFlow(DummyParentService(cfg))

    # We can pass a simple object with attributes expected by the agent.
    class Req:
        user_prompt: str = "q"
        kb_top_k: int = 7  # direct override
        thread_id: str | None = None
        parameters: dict[str, Any] | None = None  # Ensure parameters attribute exists

    resp = await flow.get_conversation_response(cast(kb.ChatRequest, Req()))
    assert "Found relevant information from Azure AI Search" in resp.agent_response
    assert len(calls) == 1
    assert calls[0]["top_k"] == 7


@pytest.mark.asyncio
async def test_kb_agent_env_override_direct(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, azure_sdk_compat: None
) -> None:
    """Verify that KB_TOPK_DIRECT environment variable overrides the direct mode default."""
    os.environ["KB_TOPK_DIRECT"] = "9"
    calls = install_fake_provider(
        monkeypatch,
        results=[{"id": "1", "title": "T", "snippet": "S", "content": "X"}],
    )

    cfg = make_config(str(tmp_path))
    flow = kb.ConversationFlow(DummyParentService(cfg))

    resp = await flow.get_conversation_response(kb.ChatRequest(user_prompt="q"))
    assert "Found relevant information from Azure AI Search" in resp.agent_response
    assert len(calls) == 1
    assert calls[0]["top_k"] == 9


@pytest.mark.asyncio
async def test_kb_agent_env_override_assist(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, azure_sdk_compat: None
) -> None:
    """Verify that KB_TOPK_ASSIST environment variable overrides the assist mode default."""
    os.environ["KB_MODE"] = "assist"
    os.environ["KB_TOPK_ASSIST"] = "11"

    calls = install_fake_provider(
        monkeypatch,
        results=[{"id": "1", "title": "T", "snippet": "S", "content": "X"}],
    )

    cfg = make_config(str(tmp_path))
    flow = kb.ConversationFlow(DummyParentService(cfg))

    resp = await flow.get_conversation_response(kb.ChatRequest(user_prompt="q"))
    assert "Found relevant information from Azure AI Search" in resp.agent_response
    assert len(calls) == 1
    assert calls[0]["top_k"] == 11


@pytest.mark.asyncio
async def test_kb_agent_snippet_fallbacks_to_content_when_missing(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, azure_sdk_compat: None
) -> None:
    """Verify that document content is used in the output if a snippet is missing."""
    # Ensure no truncation cap leaks from other tests
    monkeypatch.setenv("KB_AZURE_SNIPPET_CAP", "0")
    calls = install_fake_provider(
        monkeypatch,
        results=[{"id": "1", "title": "T", "content": "Only content"}],  # no snippet
    )

    cfg = make_config(str(tmp_path))
    flow = kb.ConversationFlow(DummyParentService(cfg))

    resp = await flow.get_conversation_response(kb.ChatRequest(user_prompt="q"))
    out = resp.agent_response

    assert "Found relevant information from Azure AI Search" in out
    assert "Only content" in out  # content is printed when snippet missing
    assert len(calls) == 1
    assert calls[0]["top_k"] == 3


@pytest.mark.asyncio
async def test_kb_agent_warns_when_no_env_default_index(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    azure_sdk_compat: None,
) -> None:
    """Verify a warning is logged when no index is configured and no env default is set."""
    # index is missing and no env override → we should warn about fallback 'test-index'
    cfg = make_config(str(tmp_path), index_name="")
    calls = install_fake_provider(
        monkeypatch,
        results=[{"id": "1", "title": "T", "snippet": "S", "content": "X"}],
    )

    flow = kb.ConversationFlow(DummyParentService(cfg))
    caplog.set_level(logging.WARNING)

    _ = await flow.get_conversation_response(kb.ChatRequest(user_prompt="q"))

    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("fallback default 'test-index'" in (m or "") for m in warnings)
    assert len(calls) == 1
