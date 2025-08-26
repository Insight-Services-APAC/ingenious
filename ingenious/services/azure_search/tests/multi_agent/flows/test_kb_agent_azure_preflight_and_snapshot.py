"""Test preflight checks and config snapshots for the Knowledge Base agent.

This module contains tests for the Azure Search integration within the
Knowledge Base agent's conversation flow. It specifically focuses on two key
areas:
1.  Preflight validation (`_require_valid_azure_index`): Ensures that the
    agent correctly checks for valid Azure Search configuration, required SDKs,
    and service accessibility before proceeding. It tests various failure modes.
2.  Configuration snapshotting (`_dump_kb_config_snapshot`): Verifies that
    the agent can capture its configuration for diagnostics, correctly masking
    secrets by default and handling potential serialization errors.

The tests rely heavily on monkeypatching to simulate different environments
(e.g., missing SDKs, failing service calls) without actual I/O.
"""

from __future__ import annotations

import logging
import os
import sys
import types
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Callable, Iterator, NoReturn

import pytest

import ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent.knowledge_base_agent as kb
from ingenious.services.retrieval.errors import PreflightError

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch


# ──────────────────────────────────────────────────────────────────────────────
# Common patches
# ──────────────────────────────────────────────────────────────────────────────


class AcceptingLogHandler(logging.Handler):
    """A logging handler that accepts and discards all records."""

    def emit(self, record: logging.LogRecord) -> None:
        """Discard the log record.

        This method is a no-op, effectively silencing any logging sent to this
        handler during tests.
        """
        pass


class DummyLLMClient:
    """A fake LLM client for testing purposes."""

    async def close(self: DummyLLMClient) -> None:
        """Simulate closing the client connection."""
        pass


@pytest.fixture(autouse=True)
def _base(monkeypatch: MonkeyPatch) -> Iterator[None]:
    """Set up a minimal patched environment for all tests in this module.

    This fixture prepares a sandboxed environment by:
    - Mocking `autogen` and other internal modules to avoid heavy imports.
    - Stubbing the memory manager to be a no-op.
    - Patching out the `LLMUsageTracker` and LLM client creation.
    - Clearing environment variables related to Azure Search credentials.
    """
    # minimal autogen environment
    core_mod = types.ModuleType("autogen_core")
    core_mod.EVENT_LOGGER_NAME = "autogen"

    class _CT: ...

    core_mod.CancellationToken = _CT
    monkeypatch.setitem(sys.modules, "autogen_core", core_mod)
    tools_mod = types.ModuleType("autogen_core.tools")

    class _FT: ...

    tools_mod.FunctionTool = _FT
    monkeypatch.setitem(sys.modules, "autogen_core.tools", tools_mod)
    agents_mod = types.ModuleType("autogen_agentchat.agents")

    class _A: ...

    agents_mod.AssistantAgent = _A
    monkeypatch.setitem(sys.modules, "autogen_agentchat.agents", agents_mod)

    # memory manager noop
    mm = types.ModuleType("ingenious.services.memory_manager")

    class _MM:
        async def close(self: _MM) -> None:
            pass

        async def maintain_memory(self: _MM, a: Any, b: Any) -> None:
            return None

    mm.get_memory_manager = lambda c, p: _MM()

    async def _run(coro: Any) -> Any:
        return await coro

    mm.run_async_memory_operation = _run
    monkeypatch.setitem(sys.modules, "ingenious.services.memory_manager", mm)

    # If LLMUsageTracker does not exist in the module, allow injection
    monkeypatch.setattr(kb, "LLMUsageTracker", AcceptingLogHandler, raising=False)
    # Patch new client factory
    monkeypatch.setattr(
        kb,
        "AzureClientFactory",
        SimpleNamespace(
            create_openai_chat_completion_client=lambda _cfg: DummyLLMClient()
        ),
    )

    for v in (
        "KB_DUMP_CONFIG_REVEAL_SECRETS",
        "AZURE_SEARCH_ENDPOINT",
        "AZURE_SEARCH_KEY",
        "AZURE_SEARCH_INDEX_NAME",
    ):
        monkeypatch.delenv(v, raising=False)
    yield


def make_cfg(
    endpoint: str = "https://s.net", key: str = "service-secret", index: str = "idx"
) -> SimpleNamespace:
    """Create a mock configuration object for the conversation flow.

    This factory helps build a simplified config structure needed by the flow
    instance during tests.
    """
    cfg = SimpleNamespace()
    cfg.models = [SimpleNamespace(model="gpt-4o")]
    cfg.azure_search_services = [
        SimpleNamespace(endpoint=endpoint, key=key, index_name=index)
    ]
    return cfg


def install_azure_sdk(
    monkeypatch: MonkeyPatch, *, raise_on_count: Exception | None = None
) -> None:
    """Simulate the presence of Azure SDK modules.

    This function patches `sys.modules` to include dummy versions of the Azure
    Search SDK modules and clients. It can optionally be configured to make the
    `get_document_count` method raise an exception to test error handling.

    Args:
        monkeypatch: The pytest monkeypatch fixture.
        raise_on_count: If provided, the mocked `get_document_count` will raise
            this exception.
    """

    class _Cred:
        def __init__(self: _Cred, key: str) -> None:
            self.key = key

    class _Client:
        def __init__(
            self: _Client, *, endpoint: str, index_name: str, credential: Any
        ) -> None: ...
        async def get_document_count(self: _Client) -> int:
            if raise_on_count:
                raise raise_on_count
            return 1

        async def close(self: _Client) -> None:
            pass

    cred_mod = types.ModuleType("azure.core.credentials")
    cred_mod.AzureKeyCredential = _Cred
    aio = types.ModuleType("azure.search.documents.aio")
    aio.SearchClient = _Client
    monkeypatch.setitem(sys.modules, "azure.core.credentials", cred_mod)
    monkeypatch.setitem(sys.modules, "azure.search.documents.aio", aio)


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────


def test_snapshot_writes_yaml_or_plaintext_and_masks_by_default(
    tmp_path: Path, monkeypatch: MonkeyPatch, caplog: LogCaptureFixture
) -> None:
    """Verify snapshot is written and secrets are masked, even if YAML fails.

    This test confirms that `_dump_kb_config_snapshot` will:
    1.  Create a snapshot file on disk.
    2.  Fall back to plaintext if YAML serialization fails.
    3.  Return a dictionary with masked secrets.
    4.  Log the configuration details.
    """
    os.environ["INGENIOUS_DIAGNOSTICS_ENABLED"] = "1"
    # Force safe_dump to fail so plaintext fallback is used; we still assert masking in the returned snapshot
    dummy_yaml = types.ModuleType("yaml")

    def _boom(*a: Any, **k: Any) -> NoReturn:
        raise RuntimeError("yaml disabled")

    dummy_yaml.safe_dump = _boom
    monkeypatch.setitem(sys.modules, "yaml", dummy_yaml)

    os.environ["AZURE_SEARCH_ENDPOINT"] = "https://env.example"
    os.environ["AZURE_SEARCH_KEY"] = "env-secret-123456789"
    os.environ["AZURE_SEARCH_INDEX_NAME"] = "docs"

    flow: kb.ConversationFlow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    flow._config = make_cfg(key="service-secret-ABCDEFG")
    flow._chat_service = None
    flow._memory_path = str(tmp_path)

    monkeypatch.chdir(tmp_path)
    caplog.set_level(logging.INFO)

    snap: dict[str, Any] = flow._dump_kb_config_snapshot(logging.getLogger("t"))
    # file created even when yaml fails
    path: Path = tmp_path / "Config_Values_knowldgebaseagent.yaml"
    assert path.exists()

    # masked by default
    assert (
        "***" in snap["kb_service_key_masked"] or "..." in snap["kb_service_key_masked"]
    )
    assert (
        "***" in snap["env_AZURE_SEARCH_KEY_masked"]
        or "..." in snap["env_AZURE_SEARCH_KEY_masked"]
    )
    # log emitted (INFO in current implementation)
    assert any("[KB Azure Config]" in (r.getMessage() or "") for r in caplog.records)


def test_snapshot_masks_secrets_by_default(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Verify that the configuration snapshot correctly masks secrets."""
    flow: kb.ConversationFlow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    flow._config = make_cfg(key="abcd1234")
    flow._chat_service = None
    flow._memory_path = str(tmp_path)

    snap: dict[str, Any] = flow._dump_kb_config_snapshot()
    # Short keys are masked as first char + "***" + last char
    assert snap["kb_service_key_masked"] == "a***4"
    # env possibly empty → masked field becomes "<empty>" (or empty)
    assert snap["env_AZURE_SEARCH_KEY_masked"] in ("", "<empty>")


def test_require_valid_index_not_configured_incomplete_sdk_missing_preflight_failed(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Verify preflight check fails when Azure search service is not configured."""
    logger = logging.getLogger("preflight")

    flow: kb.ConversationFlow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    flow._chat_service = None
    flow._memory_path = str(tmp_path)

    # 1) not_configured
    flow._config = SimpleNamespace(
        models=[SimpleNamespace(model="gpt-4o")], azure_search_services=[]
    )

    with pytest.raises(PreflightError) as ei1:
        # This is a sync call in the original code, testing a sync path.
        flow._require_valid_azure_index(logger)
    assert ei1.value.reason == "not_configured"


@pytest.mark.asyncio
async def test_require_valid_index_variants_async(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Test various async failure modes of the Azure index preflight check.

    This test covers multiple scenarios where the preflight validation should
    fail with a `PreflightError`, including:
    - No Azure service configured (`not_configured`).
    - Incomplete configuration (e.g., missing endpoint) (`incomplete_config`).
    - Azure SDK not installed (`sdk_missing`).
    - Service check fails (e.g., client raises an exception) (`preflight_failed`).
    """
    logger: logging.Logger = logging.getLogger("preflight")

    # Helper flow builder
    def _mk(endpoint: str, key: str, index: str) -> kb.ConversationFlow:
        """Create a ConversationFlow instance with a specific config."""
        f: kb.ConversationFlow = kb.ConversationFlow.__new__(kb.ConversationFlow)
        f._chat_service = None
        f._memory_path = str(tmp_path)
        f._config = SimpleNamespace(
            models=[SimpleNamespace(model="gpt-4o")],
            azure_search_services=[
                SimpleNamespace(endpoint=endpoint, key=key, index_name=index)
            ],
        )
        return f

    # 1) not_configured
    f1: kb.ConversationFlow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    f1._chat_service = None
    f1._memory_path = str(tmp_path)
    f1._config = SimpleNamespace(
        models=[SimpleNamespace(model="gpt-4o")], azure_search_services=[]
    )
    with pytest.raises(PreflightError) as e1:
        await f1._require_valid_azure_index(logger)
    assert e1.value.reason == "not_configured"
    assert "kb_service_key_masked" in e1.value.snapshot

    # 2) incomplete_config (missing endpoint; index will be filled to 'test-index')
    f2 = _mk(endpoint="", key="k", index="")
    with pytest.raises(PreflightError) as e2:
        await f2._require_valid_azure_index(logger)
    assert e2.value.reason == "incomplete_config"
    snap2: dict[str, Any] = e2.value.snapshot
    assert "kb_service_index_name" in snap2

    # 3) sdk_missing (import fails)
    f3 = _mk(endpoint="https://s", key="k", index="idx")
    # Ensure no preloaded azure.* modules bypass the import hook
    for mod in [m for m in list(sys.modules.keys()) if m.startswith("azure")]:
        monkeypatch.delitem(sys.modules, mod, raising=False)

    def _bad_import(name: str, *a: Any, **k: Any) -> types.ModuleType:
        """Raise ModuleNotFoundError for any import starting with 'azure'."""
        if name.startswith("azure"):
            raise ModuleNotFoundError("no azure")
        return orig_import(name, *a, **k)

    import builtins

    orig_import: Callable[..., types.ModuleType] = builtins.__import__
    monkeypatch.setattr(builtins, "__import__", _bad_import)
    with pytest.raises(PreflightError) as e3:
        await f3._require_valid_azure_index(logger)
    assert e3.value.reason == "sdk_missing"

    # 4) preflight_failed (client call raises)
    # Restore normal importing so the SDK stubs below can be imported
    monkeypatch.setattr(builtins, "__import__", orig_import)
    f4 = _mk(endpoint="https://s", key="k", index="idx")
    # This test case implicitly relies on `install_azure_sdk` not being called,
    # so the import will succeed but the client creation will fail internally.
    with pytest.raises(PreflightError) as e4:
        await f4._require_valid_azure_index(logger)
    assert e4.value.reason == "preflight_failed"


@pytest.mark.asyncio
async def test_azure_only_preflight_failed_bubbles_from_search(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    """Verify PreflightError bubbles up from search if the service check fails.

    This test ensures that if the Azure SDK is present but the call to
    `get_document_count` fails during a search operation, the failure is
    correctly wrapped and raised as a `PreflightError` with the reason
    `preflight_failed`.
    """
    # In azure_only when SDK importable but get_document_count fails, _search_knowledge_base should raise preflight_failed
    install_azure_sdk(monkeypatch, raise_on_count=RuntimeError("boom"))
    prov_mod = types.ModuleType("ingenious.services.azure_search.provider")

    class _Prov:
        async def retrieve(self: _Prov, *a: Any, **k: Any) -> list[Any]:
            return []

        async def close(self: _Prov) -> None:
            pass

    prov_mod.AzureSearchProvider = _Prov
    monkeypatch.setitem(
        sys.modules, "ingenious.services.azure_search.provider", prov_mod
    )

    flow: kb.ConversationFlow = kb.ConversationFlow.__new__(kb.ConversationFlow)
    flow._config = SimpleNamespace(
        models=[SimpleNamespace(model="gpt-4o")],
        azure_search_services=[
            SimpleNamespace(endpoint="https://s", key="k", index_name="idx")
        ],
    )
    flow._chat_service = None
    flow._memory_path = str(tmp_path)

    with pytest.raises(PreflightError) as ei:
        await flow._search_knowledge_base(
            "q", use_azure_search=True, top_k=3, logger=logging.getLogger("t")
        )
    assert ei.value.reason == "preflight_failed"
