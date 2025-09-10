# tests/chatstack/conftest.py

from __future__ import annotations

import json
import os
import sys
import tempfile
import types
from types import SimpleNamespace
from typing import Any, AsyncIterator, Callable

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.routing import APIRoute

from ingenious.models.chat import ChatRequest, ChatResponse, ChatResponseChunk

# ------------------------------ Constants ---------------------------------- #

BASE_URL: str = "http://test"
API_PREFIX: str = "/api/v1"
STREAM_ENDPOINT: str = f"{API_PREFIX}/chat/stream"
SAMPLE_PROMPT: str = "hello world"
SSE_PREFIX: str = "data: "

# Force-enable the httpx app= shim in ingenious.api.routes.chat
os.environ.setdefault("INGENIOUS_ENABLE_HTTPX_APP_SHIM", "1")


# ----------------------------- SSE helpers --------------------------------- #

def parse_sse_lines(raw: bytes) -> list[str]:
    text = raw.decode("utf-8", "replace")
    parts = text.split("\n\n")
    frames: list[str] = []
    for part in parts:
        if part and part.startswith(SSE_PREFIX):
            frames.append(part + "\n\n")
    return frames


def iter_sse_json(frames: list[str]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for frame in frames:
        assert frame.startswith(SSE_PREFIX)
        payload = frame[len(SSE_PREFIX):].strip()
        out.append(json.loads(payload))
    return out


# --------------------------- Autogen / Azure stubs ------------------------- #

@pytest.fixture(name="patch_autogen_stack")
def fixture_patch_autogen_stack(monkeypatch: pytest.MonkeyPatch) -> None:
    # autogen_agentchat.agents
    agents_mod = types.ModuleType("autogen_agentchat.agents")

    class AssistantAgent:
        _stream_messages: list[object] = []
        _raise_at_index: int | None = None

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._args = args
            self._kwargs = kwargs

        @classmethod
        def configure_stream(
            cls, messages: list[object], raise_at_index: int | None = None
        ) -> None:
            cls._stream_messages = list(messages)
            cls._raise_at_index = raise_at_index

        async def on_messages(self, *args: Any, **kwargs: Any) -> Any:
            return SimpleNamespace(chat_message=SimpleNamespace(content="OK"))

        async def run_stream(self, *args: Any, **kwargs: Any):
            for idx, msg in enumerate(self.__class__._stream_messages):
                if self.__class__._raise_at_index is not None and idx == self.__class__._raise_at_index:
                    raise RuntimeError("configured stream failure")
                yield msg

    agents_mod.AssistantAgent = AssistantAgent

    # autogen_agentchat.messages
    messages_mod = types.ModuleType("autogen_agentchat.messages")

    class TextMessage:
        def __init__(self, content: str, source: str) -> None:
            self.content = content
            self.source = source

    messages_mod.TextMessage = TextMessage

    # autogen_core
    core_mod = types.ModuleType("autogen_core")

    class CancellationToken:
        def cancel(self) -> None:  # pragma: no cover
            return None

    core_mod.EVENT_LOGGER_NAME = "autogen.core"
    core_mod.CancellationToken = CancellationToken

    # autogen_core.tools
    tools_mod = types.ModuleType("autogen_core.tools")

    class FunctionTool:
        def __init__(self, func, description: str = "") -> None:
            self.func = func
            self.description = description

        async def __call__(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
            return await self.func(*args, **kwargs)

    tools_mod.FunctionTool = FunctionTool

    # Register stubs
    monkeypatch.setitem(sys.modules, "autogen_agentchat.agents", agents_mod)
    monkeypatch.setitem(sys.modules, "autogen_agentchat.messages", messages_mod)
    monkeypatch.setitem(sys.modules, "autogen_core", core_mod)
    monkeypatch.setitem(sys.modules, "autogen_core.tools", tools_mod)

    # Token counter used by several flows
    token_counter_mod = types.ModuleType("ingenious.utils.token_counter")

    def _num_tokens_from_messages(msgs: list[dict[str, Any]], model: str) -> int:
        text = " ".join(str(m.get("content", "")) for m in msgs)
        return max(0, len(text) // 4)

    token_counter_mod.num_tokens_from_messages = _num_tokens_from_messages  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ingenious.utils.token_counter", token_counter_mod)

    # Memory manager used by ConversationFlow base
    mem_mgr_mod = types.ModuleType("ingenious.services.memory_manager")

    def get_memory_manager(_cfg: Any, _path: str) -> Any:
        return SimpleNamespace(maintain_memory=lambda *_a, **_k: "ok")

    def run_async_memory_operation(x: Any) -> Any:
        return x

    mem_mgr_mod.get_memory_manager = get_memory_manager  # type: ignore[attr-defined]
    mem_mgr_mod.run_async_memory_operation = run_async_memory_operation  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ingenious.services.memory_manager", mem_mgr_mod)

    # Azure Search client factory stub
    client_init_mod = types.ModuleType("ingenious.services.azure_search.client_init")

    async def _make_async_search_client(_cfg: Any) -> Any:  # pragma: no cover
        class _Dummy:
            async def get_document_count(self) -> int:
                return 0
            async def close(self) -> None:
                return None
        return _Dummy()

    client_init_mod.make_async_search_client = _make_async_search_client  # type: ignore[attr-defined]
    monkeypatch.setitem(
        sys.modules, "ingenious.services.azure_search.client_init", client_init_mod
    )


# ----------------------- Stub FileStorage globally (autouse) --------------- #

@pytest.fixture(autouse=True)
def _patch_filestorage(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    base = os.path.join(tmp_path, "fs")
    os.makedirs(base, exist_ok=True)

    class _FS:
        def __init__(self, _cfg: Any) -> None:
            self._base = base

        async def get_prompt_template_path(self, _rev: str) -> str:
            return self._base

        async def read_file(self, *, file_name: str, file_path: str) -> str | None:
            p = os.path.join(file_path, file_name)
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                return None

        async def write_file(self, content: str, file_name: str, file_path: str) -> None:
            os.makedirs(file_path, exist_ok=True)
            with open(os.path.join(file_path, file_name), "w", encoding="utf-8") as f:
                f.write(content)

    monkeypatch.setattr(
        "ingenious.files.files_repository.FileStorage", _FS, raising=True
    )


# ----------------------- Fake ChatHistoryRepository ------------------------- #

class _FakeRepo:
    def __init__(self) -> None:
        self.messages: list[Any] = []
        self.memories: list[Any] = []
        self.calls: list[str] = []
    async def add_message(self, msg: Any) -> str:
        self.calls.append("add_message")
        self.messages.append(msg)
        return f"msg-{len(self.messages)}"
    async def add_memory(self, msg: Any) -> str:
        self.calls.append("add_memory")
        self.memories.append(msg)
        return f"mem-{len(self.memories)}"
    async def get_thread_messages(self, _thread_id: str) -> list[Any]:
        return list(self.messages)

@pytest.fixture(name="fake_repo")
def fixture_fake_repo() -> _FakeRepo:
    return _FakeRepo()


# -------------------------- Multi-agent config maker ------------------------ #

@pytest.fixture(name="make_min_multi_config")
def fixture_make_min_multi_config(tmp_path: Any) -> Callable[..., Any]:
    def _make(*, chunk_size: int = 50, protocol: int | None = None, **extras: Any) -> Any:
        mem_root = tempfile.mkdtemp(prefix="streaming_mem_", dir=str(tmp_path))
        web = SimpleNamespace(streaming_chunk_size=chunk_size)
        if protocol is not None:
            setattr(web, "stream_protocol_version", protocol)
            
        cfg = SimpleNamespace(
            web=web,
            chat_service=SimpleNamespace(enable_builtin_workflows=True),
            openai_service_instance=object(),
            chat_history=SimpleNamespace(memory_path=str(tmp_path)),
            models=[SimpleNamespace(model="stub")],
            # Add this file_storage attribute
            file_storage=SimpleNamespace(
                provider="local",
                base_path=str(tmp_path),
                data=SimpleNamespace(add_sub_folders=True)
            )
        )
        # allow tests to tack on arbitrary fields (e.g., conversation_flow)
        for k, v in extras.items():
            setattr(cfg, k, v)
        return cfg
    return _make


# ---------------------------- get_config patch ------------------------------ #

@pytest.fixture(name="patch_config_get_config")
def fixture_patch_config_get_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    model = SimpleNamespace(
        model="gpt-fake",
        api_key="key",
        base_url="http://local",
        deployment="dep",
        api_version="2024-01-01",
        authentication_method="key",
    )
    chat_history = SimpleNamespace(memory_path=str(tmp_path / "memory"))
    file_storage = SimpleNamespace(provider="local", base_path=str(tmp_path / "fs"))
    data = SimpleNamespace()
    cfg = SimpleNamespace(models=[model], chat_history=chat_history, file_storage=file_storage, data=data)
    monkeypatch.setattr("ingenious.config.config.get_config", lambda: cfg)


# --------------------------- OpenAI client stub ----------------------------- #

@pytest.fixture(name="stub_openai_factory")
def fixture_stub_openai_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Dummy:
        async def close(self) -> None:
            return None
    monkeypatch.setattr(
        "ingenious.client.azure.AzureClientFactory.create_openai_chat_completion_client",
        lambda *a, **k: _Dummy(),
    )


# ----------------------------- API app + DI -------------------------------- #

class FakeChatService:
    """Default service used by SSE tests; API tests can override dynamically."""
    def __init__(self, exception: BaseException | None = None) -> None:
        self._exception = exception

    def raise_next(self, exc: BaseException) -> None:
        self._exception = exc

    async def get_chat_response(self, chat_request: ChatRequest) -> ChatResponse:
        # Echo provided thread_id; if missing, generate a stable one so tests can assert deterministically
        tid = chat_request.thread_id or "t-abc"
        return ChatResponse(
            thread_id=tid,
            message_id="m1",
            agent_response="ok",
            token_count=0,
            max_token_count=0,
            memory_summary="",
        )

    async def get_streaming_chat_response(
        self, chat_request: ChatRequest
    ) -> AsyncIterator[ChatResponseChunk]:
        if self._exception is not None:
            exc = self._exception
            self._exception = None
            raise exc
        yield ChatResponseChunk(
            thread_id=chat_request.thread_id or "t1",
            message_id="m1",
            chunk_type="content",
            content="he",
            is_final=False,
        )
        yield ChatResponseChunk(
            thread_id="",  # force backfill
            message_id="",
            chunk_type="content",
            content="llo",
            is_final=False,
        )


def _rebind_dependencies_to_dynamic_lookup(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Make route dependencies dynamic: instead of calling the function object captured
    at router build time, call a small wrapper that looks up the module attribute
    (which tests can monkeypatch) on every request.
    """
    import ingenious.api.routes.chat as chat_mod  # noqa: WPS433

    # 1) Ensure SSE JSON excludes None (so 'done' => {"event":"done"})
    def _dump_json_excluding_none(payload: Any) -> str:
        # Prefer pydantic v2 path if available
        to_dump = getattr(payload, "model_dump", None)
        if callable(to_dump):
            try:
                return json.dumps(to_dump(exclude_none=True), ensure_ascii=False)
            except Exception:
                pass
        # Try v1 .dict()
        to_dict = getattr(payload, "dict", None)
        if callable(to_dict):
            try:
                d = to_dict()
                # drop nulls recursively (shallow is enough for StreamingChatResponse)
                d = {k: v for k, v in d.items() if v is not None}
                return json.dumps(d, ensure_ascii=False)
            except Exception:
                pass
        # Last resort: json.dumps and hope payload is plain dict
        try:
            if isinstance(payload, dict):
                d = {k: v for k, v in payload.items() if v is not None}
                return json.dumps(d, ensure_ascii=False)
        except Exception:
            pass
        return json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr(chat_mod, "_dump_json", _dump_json_excluding_none, raising=False)

    # 2) Default test-friendly providers (tests can override later)
    monkeypatch.setattr(chat_mod, "get_conditional_security", lambda: "test_user", raising=False)
    monkeypatch.setattr(chat_mod, "get_chat_service", lambda: FakeChatService(), raising=False)

    # 3) Dynamic wrappers used by the routes
    async def _dynamic_chat_service_provider() -> Any:
        provider = getattr(chat_mod, "get_chat_service")
        return provider()  # provider returns a service instance

    def _dynamic_security_provider() -> Any:
        provider = getattr(chat_mod, "get_conditional_security")
        return provider()

    # 4) Replace the dependant.call on each route where appropriate
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for dep in route.dependant.dependencies:
            # swap the call target for our dynamic wrappers
            if getattr(dep.call, "__name__", "") == "get_chat_service":
                dep.call = _dynamic_chat_service_provider
            elif getattr(dep.call, "__name__", "") == "get_conditional_security":
                dep.call = _dynamic_security_provider


@pytest.fixture(name="app")
def fixture_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    # Avoid side-effectful namespace discovery
    monkeypatch.setattr(
        "ingenious.utils.namespace_utils.print_namespace_modules", lambda *a, **k: None
    )

    from ingenious.api.routes.chat import router  # import after env var is set

    app = FastAPI()
    app.include_router(router, prefix=API_PREFIX)

    # Rebind dependencies so tests can monkeypatch get_chat_service/security *after* app creation
    _rebind_dependencies_to_dynamic_lookup(app, monkeypatch)

    os.environ["INGENIOUS_DIAGNOSTICS_ENABLED"] = "0"
    return app


# -------------------------- HTTPX client fixture --------------------------- #

def _make_async_client(app: FastAPI) -> httpx.AsyncClient:
    """
    Build with `app=` so tests can reach `_transport.app` even on httpx>=0.28.
    The router module patches httpx __init__ to accept `app=`.
    """
    try:
        return httpx.AsyncClient(app=app, base_url=BASE_URL, timeout=10.0)
    except TypeError:
        transport = httpx.ASGITransport(app=app)
        return httpx.AsyncClient(transport=transport, base_url=BASE_URL, timeout=10.0)


@pytest_asyncio.fixture(name="async_client")
async def fixture_async_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    client = _make_async_client(app)
    async with client:
        yield client
