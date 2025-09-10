"""KB policy enforcement and diagnostics masking tests.

Why:
- Ensure `azure_only` policy denies local fallback (compliance/safety).
- Ensure diagnostics snapshot masks secrets and only writes when enabled.

Usage:
- Pure unit tests; no external services required.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from ingenious.models.chat import ChatRequest
from ingenious.services.chat_services.multi_agent.conversation_flows.knowledge_base_agent.knowledge_base_agent import (  # noqa: E501
    ConversationFlow as KBFlow,
)
from ingenious.services.retrieval.errors import PreflightError

FILENAME: str = "Config_Values_knowldgebaseagent.yaml"
RAW_KEY: str = "abcd1234wxyz9876"
MASK_PREFIX: str = "abcd"
MASK_SUFFIX: str = "9876"


@pytest.mark.asyncio
async def test_kb_policy_azure_only_denies_local_fallback(
    tmp_path: Path,
) -> None:
    """KB flow must not fall back to local when policy is azure_only.

    Intent:
    - With no Azure config and KB policy set to 'azure_only', direct mode must
      raise PreflightError(reason='policy').
    """
    class _Parent:
        def __init__(self) -> None:
            self.config = type(
                "Cfg",
                (),
                {
                    "chat_history": type("CH", (), {"memory_path": str(tmp_path)}),
                    "azure_search_services": [],  # No Azure
                    "knowledge_base_policy": "azure_only",
                    "models": [type("M", (), {"model": "test-model"})],
                },
            )()
            self.chat_history_repository = None

    flow = KBFlow(parent_multi_agent_chat_service=_Parent())
    req = ChatRequest(
        user_prompt="Any KB question", conversation_flow="knowledge_base_agent"
    )

    with pytest.raises(PreflightError) as ei:
        await flow.get_conversation_response(req)

    err = ei.value
    assert err.reason == "policy"


def test_kb_diagnostics_masks_secrets_and_writes_file_only_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Diagnostics snapshot should mask secrets and be opt-in.

    Intent:
    - When INGENIOUS_DIAGNOSTICS_ENABLED=1, a snapshot file is written with a
      masked key (never the raw secret).
    - When disabled, no file is written.
    """
    monkeypatch.chdir(tmp_path)

    # Enabled → file created with masked secret.
    monkeypatch.setenv("INGENIOUS_DIAGNOSTICS_ENABLED", "1")

    svc = type(
        "Svc",
        (),
        {"endpoint": "https://ex.search.windows.net", "index_name": "idx", "key": RAW_KEY},
    )
    cfg = type(
        "Cfg",
        (),
        {
            "chat_history": type("CH", (), {"memory_path": str(tmp_path)}),
            "azure_search_services": [svc],
            "knowledge_base_policy": "prefer_local",
            "models": [type("M", (), {"model": "test-model"})],
        },
    )()
    parent = type("P", (), {"config": cfg, "chat_history_repository": None})()
    flow = KBFlow(parent_multi_agent_chat_service=parent)

    snap = flow._dump_kb_config_snapshot()
    out = tmp_path / FILENAME
    assert out.exists(), "Snapshot file should be created when diagnostics enabled."

    text = out.read_text(encoding="utf-8")
    assert RAW_KEY not in text, "Raw secret must never appear in diagnostics output."
    # Mask should show prefix + ellipsis + suffix form
    assert MASK_PREFIX in text and MASK_SUFFIX in text and "..." in text
    masked: str = snap["kb_service_key_masked"]
    assert masked.startswith(MASK_PREFIX) and masked.endswith(f"{MASK_SUFFIX} (len={len(RAW_KEY)})")

    # Disabled → no file written (ensure old file removed).
    out.unlink(missing_ok=True)
    monkeypatch.setenv("INGENIOUS_DIAGNOSTICS_ENABLED", "0")
    _ = flow._dump_kb_config_snapshot()
    assert not (tmp_path / FILENAME).exists(), "No snapshot when diagnostics disabled."
