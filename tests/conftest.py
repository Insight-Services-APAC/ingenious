"""Project-wide pytest fixtures with strong isolation and safe defaults.

This conftest module hardens tests to be deterministic and order-independent.
Key goals:
- Isolate process environment (notably INGENIOUS_/AZURE_/OPENAI_ vars) per test.
- Reset obvious configuration singletons/LRU caches between tests.
- Provide common mocks and sample artifacts (files, configs, responses).
- Ensure external services (Azure OpenAI, HTTP) are safely stubbed when used.

Usage:
    Keep this file at the repository root or `tests/` directory so pytest
    auto-discovers it. Individual tests can opt into the fixtures as needed.
"""

from __future__ import annotations

import importlib
import os
import tempfile
from pathlib import Path
from typing import Any, Iterator, Tuple
from unittest.mock import AsyncMock, Mock, patch

import pytest

# --------------------------- Constants (no magic values) ----------------------------

ENV_PREFIXES: Tuple[str, ...] = ("INGENIOUS_", "AZURE_", "OPENAI_")
MINIMAL_PDF_BYTES: bytes = (
    b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
    b"xref\n0 4\n0000000000 65535 f\n0000000010 00000 n\n"
    b"0000000053 00000 n\n0000000100 00000 n\n"
    b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n147\n%%EOF\n"
)
MINIMAL_DOCX_ZIP_HEADER: bytes = b"PK\x03\x04\x14\x00\x00\x00\x08\x00"


# ------------------------------ Global Isolation -----------------------------------

@pytest.fixture(autouse=True)
def _isolate_env_and_config(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear sensitive env vars and reset config caches before each test.

    Why:
        Prevent cross-test pollution from process-wide environment variables and
        module-level singletons/caches that influence configuration resolution.

    Effects:
        - Removes env vars starting with ENV_PREFIXES.
        - Clears `ingenious.config.config.get_config` LRU cache (if present).
        - Resets `ingenious.config.config._CONFIG` to None (if present).
    """
    # Remove prefixed environment variables.
    for key in list(os.environ):
        if key.startswith(ENV_PREFIXES):
            monkeypatch.delenv(key, raising=False)

    # Best-effort reset of config caches/singletons if the module exists.
    try:
        cfg = importlib.import_module("ingenious.config.config")
    except ModuleNotFoundError:
        cfg = None  # type: ignore[assignment]

    if cfg is not None:
        get_config = getattr(cfg, "get_config", None)
        if getattr(get_config, "cache_clear", None):
            get_config.cache_clear()  # type: ignore[call-arg]

        if hasattr(cfg, "_CONFIG"):
            monkeypatch.setattr(cfg, "_CONFIG", None, raising=False)

    yield


# ---------------------------------- Fixtures ---------------------------------------

@pytest.fixture
def mock_env() -> Iterator[None]:
    """Provide an empty environment for tests that need a full wipe.

    Why:
        Some tests want a totally clean `os.environ`, beyond the prefix-based
        cleaning done by `_isolate_env_and_config`.
    """
    with patch.dict(os.environ, {}, clear=True):
        yield


@pytest.fixture
def mock_azure_openai() -> Iterator[Mock]:
    """Mock Azure OpenAI client constructor where the SUT imports it.

    Why:
        Avoids network calls and external dependencies during tests. Patch the
        symbol at the import location used by the SUT for correctness.
    """
    with patch(
        "ingenious.external_services.openai_service.AzureOpenAI"
    ) as mock_client:
        mock_instance = Mock()
        mock_client.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def sample_config_data() -> dict[str, Any]:
    """Return minimal yet representative configuration structure.

    Why:
        Allows tests to exercise config-driven code without real files.
    """
    return {
        "agents": [
            {"name": "test_agent", "description": "Test agent", "model": "gpt-4o-mini"}
        ],
        "workflows": {
            "test_workflow": {"agents": ["test_agent"], "description": "Test workflow"}
        },
    }


@pytest.fixture
def sample_message_data() -> dict[str, Any]:
    """Return a simple message payload for tests that need message-like input."""
    return {
        "content": "Test message content",
        "role": "user",
        "timestamp": "2023-01-01T00:00:00Z",
    }


@pytest.fixture
def mock_chat_history_repo() -> Mock:
    """Provide a simple in-memory chat history repository mock.

    Why:
        Decouples tests from persistence; defines expected interface methods.
    """
    mock_repo = Mock()
    mock_repo.get_conversation = Mock(
        return_value={"conversation_id": "test_id", "messages": []}
    )
    mock_repo.save_conversation = Mock()
    mock_repo.delete_conversation = Mock()
    return mock_repo


@pytest.fixture
def mock_openai_response() -> Any:
    """Build a minimal OpenAI ChatCompletion-like object.

    Why:
        Avoids hitting the real OpenAI client while keeping structure realistic.
    Raises:
        Skips the test if `openai`'s typed classes are unavailable.
    """
    chat_mod = pytest.importorskip("openai.types.chat")
    cc_mod = pytest.importorskip("openai.types.chat.chat_completion")

    ChatCompletion = chat_mod.ChatCompletion
    ChatCompletionMessage = chat_mod.ChatCompletionMessage
    Choice = cc_mod.Choice

    mock_message = ChatCompletionMessage(
        role="assistant", content="Test response from OpenAI"
    )
    mock_choice = Choice(index=0, message=mock_message, finish_reason="stop")
    return ChatCompletion(
        id="test_completion_id",
        choices=[mock_choice],
        created=1234567890,
        model="gpt-4o-mini",
        object="chat.completion",
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )


@pytest.fixture
def temp_dir() -> Iterator[Path]:
    """Yield a temporary directory as a Path object and clean up afterwards.

    Why:
        Many tests need a throwaway filesystem sandbox.
    """
    with tempfile.TemporaryDirectory() as temp:
        yield Path(temp)


@pytest.fixture
def sample_pdf_path() -> Iterator[Path]:
    """Create a minimal valid-looking PDF file and yield its path.

    Why:
        Tests that parse or sniff content-type need a real file path on disk.
    """
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_file:
        temp_file.write(MINIMAL_PDF_BYTES)
        temp_file.flush()
        path = Path(temp_file.name)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


@pytest.fixture
def sample_docx_path() -> Iterator[Path]:
    """Create a minimal DOCX (ZIP header) file and yield its path."""
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as temp_file:
        temp_file.write(MINIMAL_DOCX_ZIP_HEADER)
        temp_file.flush()
        path = Path(temp_file.name)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


@pytest.fixture
def mock_requests_get() -> Iterator[Mock]:
    """Mock `requests.get` to return deterministic bytes and headers.

    Why:
        Prevents real HTTP access and gives tests a stable payload to assert on.
    """
    with patch("requests.get") as mock_get:
        mock_response = Mock()
        mock_response.content = b"mock response content"
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        yield mock_get


@pytest.fixture
def mock_async_queue() -> AsyncMock:
    """Return an AsyncMock that behaves like a simple async queue.

    Why:
        Allows tests of async producers/consumers without real asyncio.Queue.
    """
    mock_queue: AsyncMock = AsyncMock()
    mock_queue.put = AsyncMock()
    mock_queue.get = AsyncMock(return_value="test message")
    mock_queue.empty = Mock(return_value=False)
    return mock_queue


@pytest.fixture
def sample_agent_config() -> dict[str, Any]:
    """Provide a representative agent configuration dictionary."""
    return {
        "name": "test_agent",
        "description": "Test agent for unit testing",
        "model": "gpt-4o-mini",
        "temperature": 0.7,
        "max_tokens": 1000,
        "system_prompt": "You are a helpful test assistant.",
    }


@pytest.fixture
def sample_workflow_config() -> dict[str, Any]:
    """Provide a representative workflow configuration dictionary."""
    return {
        "name": "test_workflow",
        "description": "Test workflow for unit testing",
        "agents": ["test_agent"],
        "steps": [
            {"type": "user_input", "prompt": "Enter your question"},
            {"type": "agent_response", "agent": "test_agent"},
        ],
    }
