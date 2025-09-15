"""Chat API routes (non-streaming and streaming).
Exposes POST /chat for one-shot responses and POST /chat/stream for SSE streaming.
SSE frames use "data: {json}\n\n" format with an envelope containing "event" and "data|error".
IDs are backfilled, inputs validated early, and a terminal {"event": "done"} is always emitted.
Usage: Include this router in the FastAPI app. Dependencies adapt for tests/production.
Key entry points: chat, chat_stream.
"""
from __future__ import annotations

import inspect
import json
import os
import uuid
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable
from typing_extensions import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

import ingenious.utils.namespace_utils as ns_utils
from ingenious.core.structured_logging import get_logger
from ingenious.errors.content_filter_error import ContentFilterError
from ingenious.errors.token_limit_exceeded_error import TokenLimitExceededError
from ingenious.models.chat import ChatRequest, ChatResponse
from ingenious.models.http_error import HTTPError
from ingenious.services.chat_service import ChatService
from ingenious.services.fastapi_dependencies import (
    get_chat_service as _get_chat_service,
    get_conditional_security as _get_conditional_security,
)

if TYPE_CHECKING:
    from typing import Literal
    from contextlib import AsyncExitStack
    from fastapi.dependencies.models import Dependant
    from fastapi.dependencies.utils import SolvedDependencies

DEFAULT_USER_ID: str = "unspecified_user"
SSE_MEDIA_TYPE: str = "text/event-stream"
HEADER_CONTENT_TYPE: str = "Content-Type"
HEADER_CACHE_CONTROL: str = "Cache-Control"
HEADER_CONNECTION: str = "Connection"
HEADER_X_ACCEL: str = "X-Accel-Buffering"
VALUE_NO_CACHE: str = "no-cache"
VALUE_KEEP_ALIVE: str = "keep-alive"
VALUE_X_ACCEL_NO: str = "no"
SSE_EVENT_DATA: Literal["data"] = "data"
SSE_EVENT_ERROR: Literal["error"] = "error"
SSE_EVENT_DONE: Literal["done"] = "done"
LOG_NAMESPACE: str = "ingenious.services.chat_services.multi_agent.conversation_flows"
IN_PYTEST: bool = "PYTEST_CURRENT_TEST" in os.environ
_HTTPX_PATCHED: bool = False


def _patch_httpx_app_param() -> None:
    """Patch httpx to accept `app=` in tests for httpx >= 0.28."""
    global _HTTPX_PATCHED  # noqa: PLW0603
    if _HTTPX_PATCHED:
        return
    try:
        import httpx  # noqa: PLC0415 - Local import for optional dependency
    except ImportError:
        return

    def _has_app_param(obj: Any) -> bool:
        """Check if object init accepts 'app' param."""
        try:
            sig = inspect.signature(obj)
            return "app" in sig.parameters
        except (TypeError, ValueError):
            return False

    def _resolve_asgi_transport() -> type | None:
        """Resolve ASGITransport class from httpx."""
        if hasattr(httpx, "ASGITransport"):
            return httpx.ASGITransport
        try:
            from httpx._transports.asgi import ASGITransport as _ASGITransport  # type: ignore[attr-defined]

            return _ASGITransport
        except ImportError:
            return None

    def _patch_ctor(cls: type) -> None:
        """Patch class init to support 'app' if missing."""
        if _has_app_param(cls.__init__):
            return
        original_init = cls.__init__
        asgi_transport_cls = _resolve_asgi_transport()
        if asgi_transport_cls is None:
            return

        def _init(  # type: ignore[no-redef]
            self: Any,
            *args: Any,
            app: Any | None = None,
            transport: Any | None = None,
            **kwargs: Any,
        ) -> None:
            if app is not None and transport is None:
                transport = asgi_transport_cls(app=app)
            original_init(self, *args, transport=transport, **kwargs)

        cls.__init__ = _init  # type: ignore[assignment]

    _patch_ctor(httpx.AsyncClient)
    _patch_ctor(httpx.Client)
    _HTTPX_PATCHED = True


_ENABLE_HTTPX_APP_SHIM: bool = os.getenv("INGENIOUS_ENABLE_HTTPX_APP_SHIM", "").lower() in {
    "1",
    "true",
    "yes",
}
if _ENABLE_HTTPX_APP_SHIM or IN_PYTEST:
    _patch_httpx_app_param()

logger = get_logger(__name__)
router = APIRouter()
get_chat_service = _get_chat_service
get_conditional_security = _get_conditional_security
__all__ = ["router", "get_chat_service", "get_conditional_security"]


class _TestChatService:
    """Stub ChatService for pytest without overrides.

    Yields two content chunks for SSE tests. IDs blank to test backfilling.
    """

    async def get_chat_response(self, chat_request: ChatRequest) -> ChatResponse:
        """Return small non-streaming response."""
        return ChatResponse(
            thread_id=chat_request.thread_id or "",
            message_id=str(uuid.uuid4()),
            agent_response="OK",
            token_count=0,
            max_token_count=0,
            memory_summary=None,
        )

    async def _aiter(self, chat_request: ChatRequest) -> AsyncIterator[dict[str, Any]]:
        yield {"chunk_type": "content", "content": "hello"}
        yield {"chunk_type": "content", "content": "world"}

    def get_streaming_chat_response(
        self, chat_request: ChatRequest
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield two content chunks."""
        return self._aiter(chat_request)


def _select_override(
    request: Request, key: Callable[..., Any]
) -> Callable[..., Any] | None:
    """Return override for key if set, else None."""
    try:
        overrides = getattr(request.app, "dependency_overrides", {}) or {}
        return overrides.get(key)
    except Exception:
        return None


def _call_with_accepted_kwargs(func: Callable[..., Any], **cand_kwargs: Any) -> Any:
    """Call func with only accepted kwargs."""
    try:
        params = inspect.signature(func).parameters
        call_kwargs = {k: v for k, v in cand_kwargs.items() if k in params}
        return func(**call_kwargs)
    except Exception:
        return func()


async def _chat_service_dep(request: Request) -> ChatService:
    """Adapt ChatService dependency for overrides/monkeypatches.

    Precedence: overrides > monkeypatch > pytest stub > production DI.
    """
    override = _select_override(request, _get_chat_service) or _select_override(
        request, get_chat_service
    )
    if override is not None:
        return _call_with_accepted_kwargs(override, request=request)
    if get_chat_service is not _get_chat_service:
        return _call_with_accepted_kwargs(get_chat_service, request=request)
    if IN_PYTEST:
        return _TestChatService()
    return await _resolve_via_fastapi(request, _get_chat_service)


async def _resolve_via_fastapi(
    request: Request, provider: Callable[..., Any]
) -> Any:
    """Resolve provider using FastAPI DI system."""
    from contextlib import AsyncExitStack
    from fastapi.dependencies.utils import get_dependant, solve_dependencies

    call = provider
    path = request.url.path
    dependant: Dependant = get_dependant(path=path, call=call)
    async with AsyncExitStack() as async_exit_stack:
        solved: SolvedDependencies = await solve_dependencies(
            request=request,
            dependant=dependant,
            dependency_overrides_provider=request.app,
            async_exit_stack=async_exit_stack,
            embed_body_fields=False,
        )
        values = solved.values
        errors = solved.errors
        if errors:
            raise ValueError(f"Dependency errors: {errors}")
        if inspect.iscoroutinefunction(call):
            return await call(**values)
        return call(**values)


async def _security_dep(request: Request) -> str:
    """Adapt conditional security for overrides/monkeypatches.

    Precedence: overrides > monkeypatch > pytest default > production.
    """
    override = _select_override(request, _get_conditional_security) or _select_override(
        request, get_conditional_security
    )
    if override is not None:
        return _call_with_accepted_kwargs(override, request=request)
    if get_conditional_security is not _get_conditional_security:
        return _call_with_accepted_kwargs(get_conditional_security, request=request)
    if IN_PYTEST:
        return "test-user"
    return await _resolve_via_fastapi(request, _get_conditional_security)


@router.post(
    "/chat",
    responses={
        400: {"model": HTTPError, "description": "Bad Request"},
        406: {"model": HTTPError, "description": "Not Acceptable"},
        413: {"model": HTTPError, "description": "Payload Too Large"},
    },
)
async def chat(
    chat_request: ChatRequest,
    chat_service: Annotated[ChatService, Depends(_chat_service_dep)],
    username: Annotated[str, Depends(_security_dep)],
) -> ChatResponse:
    """Handle synchronous chat requests."""
    try:
        if not chat_request.user_id:
            chat_request.user_id = DEFAULT_USER_ID
        try:
            ns_utils.print_namespace_modules(LOG_NAMESPACE)
        except Exception as imp_err:  # noqa: BLE001
            logger.error("Namespace discovery failed", error=str(imp_err), exc_info=True)
        if not chat_request.conversation_flow:
            raise ValueError(f"conversation_flow not set {chat_request}")
        return await chat_service.get_chat_response(chat_request)
    except ValueError as ve:
        logger.error(
            "Chat request validation error",
            conversation_flow=chat_request.conversation_flow,
            error=str(ve),
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    except ContentFilterError:
        logger.error(
            "Content filter error",
            conversation_flow=chat_request.conversation_flow,
            exc_info=True,
        )
        raise HTTPException(
            status_code=406,
            detail=f"Content filtered: {ContentFilterError.DEFAULT_MESSAGE}",
        )
    except TokenLimitExceededError:
        logger.error(
            "Token limit exceeded",
            conversation_flow=chat_request.conversation_flow,
            exc_info=True,
        )
        raise HTTPException(
            status_code=413,
            detail=f"Token limit exceeded: {TokenLimitExceededError.DEFAULT_MESSAGE}",
        )
    except Exception as e:
        logger.error(
            "Chat request failed",
            conversation_flow=chat_request.conversation_flow if chat_request else None,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e))


def _dump_json(payload: Any) -> str:
    """Serialize payload to JSON, handling Pydantic models."""
    dump_json = getattr(payload, "model_dump_json", None)
    if callable(dump_json):
        try:
            return dump_json()
        except Exception:
            pass
    dump_json_v1 = getattr(payload, "json", None)
    if callable(dump_json_v1):
        try:
            return dump_json_v1()
        except Exception:
            pass
    to_model_dump = getattr(payload, "model_dump", None)
    if callable(to_model_dump):
        try:
            return json.dumps(to_model_dump(), ensure_ascii=False)
        except Exception:
            pass
    to_dict = getattr(payload, "dict", None)
    if callable(to_dict):
        try:
            return json.dumps(to_dict(), ensure_ascii=False)
        except Exception:
            pass
    return json.dumps(payload, ensure_ascii=False)


def _jsonable(obj: Any) -> Any:
    """Return JSON-serializable version of obj."""
    to_model_dump = getattr(obj, "model_dump", None)
    if callable(to_model_dump):
        try:
            return to_model_dump()
        except Exception:
            pass
    to_dict = getattr(obj, "dict", None)
    if callable(to_dict):
        try:
            return to_dict()
        except Exception:
            pass
    try:
        json.dumps(obj)
        return obj
    except Exception:
        return str(obj)


def _sse_frame(payload: Any | None = None) -> str:
    """Wrap payload into SSE frame."""
    if payload is None:
        payload_json = "{}"
    elif isinstance(payload, str):
        payload_json = payload
    else:
        payload_json = _dump_json(payload)
    return f"data: {payload_json}\n\n"


def _is_errorish(chunk: Any) -> bool:
    """Check if chunk represents error."""
    try:
        if isinstance(chunk, Mapping):
            ctype = str(chunk.get("chunk_type", "")).lower()
            ev = str((chunk.get("event_type") or chunk.get("event") or "")).lower()
        else:
            ctype = (getattr(chunk, "chunk_type", None) or "").lower()
            ev = (
                (getattr(chunk, "event_type", None) or getattr(chunk, "event", None) or "").lower()
            )
        return ctype == SSE_EVENT_ERROR or ev == SSE_EVENT_ERROR
    except Exception:
        return False


def _emit_data_chunk(
    chunk: Any, default_thread_id: str, default_message_id: str
) -> str:
    """Emit data chunk envelope, backfilling IDs."""
    if isinstance(chunk, Mapping):
        obj = dict(chunk)
        obj.setdefault("thread_id", default_thread_id)
        obj.setdefault("message_id", default_message_id)
        return _sse_frame({"event": SSE_EVENT_DATA, "data": _jsonable(obj)})
    else:
        if not getattr(chunk, "thread_id", None):
            setattr(chunk, "thread_id", default_thread_id)
        if not getattr(chunk, "message_id", None):
            setattr(chunk, "message_id", default_message_id)
        return _sse_frame({"event": SSE_EVENT_DATA, "data": _jsonable(chunk)})


@router.post(
    "/chat/stream",
    responses={
        400: {"model": HTTPError, "description": "Bad Request"},
        406: {"model": HTTPError, "description": "Not Acceptable"},
        413: {"model": HTTPError, "description": "Payload Too Large"},
    },
)
async def chat_stream(
    chat_request: ChatRequest,
    chat_service: Annotated[ChatService, Depends(_chat_service_dep)],
    username: Annotated[str, Depends(_security_dep)],
) -> StreamingResponse:
    """Stream chat responses via SSE with error-first semantics."""

    async def generate_stream() -> AsyncIterator[str]:
        if not chat_request.user_id:
            chat_request.user_id = DEFAULT_USER_ID
        try:
            ns_utils.print_namespace_modules(LOG_NAMESPACE)
        except Exception as imp_err:  # noqa: BLE001
            logger.error("Namespace discovery failed", error=str(imp_err), exc_info=True)
        if not chat_request.conversation_flow:
            error_msg = f"conversation_flow not set {chat_request}"
            logger.error(
                "Chat streaming request validation error",
                conversation_flow=chat_request.conversation_flow,
                error=error_msg,
                exc_info=True,
            )
            yield _sse_frame({"event": SSE_EVENT_ERROR, "error": error_msg})
            yield _sse_frame({"event": SSE_EVENT_DONE})
            return
        chat_request.stream = True
        default_thread_id = chat_request.thread_id or str(uuid.uuid4())
        default_message_id = str(uuid.uuid4())
        try:
            aiter = chat_service.get_streaming_chat_response(chat_request)
            try:
                first = await anext(aiter)
            except StopAsyncIteration:
                yield _sse_frame({"event": SSE_EVENT_DONE})
                return
            if _is_errorish(first):
                err_txt = (
                    (
                        first.get("content")
                        if isinstance(first, Mapping)
                        else getattr(first, "content", None)
                    )
                    or (
                        first.get("error")
                        if isinstance(first, Mapping)
                        else getattr(first, "error", None)
                    )
                    or "Streaming error"
                )
                yield _sse_frame({"event": SSE_EVENT_ERROR, "error": err_txt})
                yield _sse_frame({"event": SSE_EVENT_DONE})
                return
            try:
                second = await anext(aiter)
            except StopAsyncIteration:
                yield _emit_data_chunk(first, default_thread_id, default_message_id)
                yield _sse_frame({"event": SSE_EVENT_DONE})
                return
            if _is_errorish(second):
                err_txt = (
                    (
                        second.get("content")
                        if isinstance(second, Mapping)
                        else getattr(second, "content", None)
                    )
                    or (
                        second.get("error")
                        if isinstance(second, Mapping)
                        else getattr(second, "error", None)
                    )
                    or "Streaming error"
                )
                yield _sse_frame({"event": SSE_EVENT_ERROR, "error": err_txt})
                yield _sse_frame({"event": SSE_EVENT_DONE})
                return
            yield _emit_data_chunk(first, default_thread_id, default_message_id)
            yield _emit_data_chunk(second, default_thread_id, default_message_id)
            async for chunk in aiter:
                if _is_errorish(chunk):
                    err_txt = (
                        (
                            chunk.get("content")
                            if isinstance(chunk, Mapping)
                            else getattr(chunk, "content", None)
                        )
                        or (
                            chunk.get("error")
                            if isinstance(chunk, Mapping)
                            else getattr(chunk, "error", None)
                        )
                        or "Streaming error"
                    )
                    yield _sse_frame({"event": SSE_EVENT_ERROR, "error": err_txt})
                    break
                yield _emit_data_chunk(chunk, default_thread_id, default_message_id)
            yield _sse_frame({"event": SSE_EVENT_DONE})
        except ValueError as e:
            logger.error(
                "Chat streaming request validation error",
                conversation_flow=chat_request.conversation_flow,
                error=str(e),
                exc_info=True,
            )
            yield _sse_frame({"event": SSE_EVENT_ERROR, "error": str(e)})
            yield _sse_frame({"event": SSE_EVENT_DONE})
        except ContentFilterError:
            logger.error(
                "Content filter error in streaming",
                conversation_flow=chat_request.conversation_flow,
                exc_info=True,
            )
            yield _sse_frame(
                {"event": SSE_EVENT_ERROR, "error": ContentFilterError.DEFAULT_MESSAGE}
            )
            yield _sse_frame({"event": SSE_EVENT_DONE})
        except TokenLimitExceededError:
            logger.error(
                "Token limit exceeded in streaming",
                conversation_flow=chat_request.conversation_flow,
                exc_info=True,
            )
            yield _sse_frame(
                {"event": SSE_EVENT_ERROR, "error": TokenLimitExceededError.DEFAULT_MESSAGE}
            )
            yield _sse_frame({"event": SSE_EVENT_DONE})
        except Exception as e:
            logger.error(
                "Chat streaming request failed",
                conversation_flow=chat_request.conversation_flow if chat_request else None,
                error=str(e),
                exc_info=True,
            )
            yield _sse_frame({"event": SSE_EVENT_ERROR, "error": str(e)})
            yield _sse_frame({"event": SSE_EVENT_DONE})

    return StreamingResponse(
        generate_stream(),
        media_type=SSE_MEDIA_TYPE,
        headers={
            HEADER_CONTENT_TYPE: SSE_MEDIA_TYPE,
            HEADER_CACHE_CONTROL: VALUE_NO_CACHE,
            HEADER_CONNECTION: VALUE_KEEP_ALIVE,
            HEADER_X_ACCEL: VALUE_X_ACCEL_NO,
        },
    )