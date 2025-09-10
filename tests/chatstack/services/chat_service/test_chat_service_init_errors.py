"""ChatService constructor error mapping tests.

Why:
- Ensure ImportError during backend resolution maps to ChatServiceError with context.
"""

from __future__ import annotations

import pytest

from ingenious.errors import ChatServiceError
from ingenious.services.chat_service import ChatService

SERVICE_TYPE: str = "nonexistent"
FLOW_NAME: str = "any_flow"


def test_chat_service_import_error_maps_to_chatserviceerror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Constructor should surface a ChatServiceError with clear context on ImportError."""
    def _boom(*_a: object, **_k: object) -> object:
        raise ImportError("boom")

    # Patch the symbol as imported into the module under test.
    monkeypatch.setattr(
        "ingenious.services.chat_service.import_class_with_fallback",
        _boom,
        raising=True,
    )

    cfg = type("Cfg", (), {"models": [type("M", (), {"model": "m"})]})()
    repo = object()

    with pytest.raises(ChatServiceError) as ei:
        ChatService(SERVICE_TYPE, repo, FLOW_NAME, cfg)

    err = ei.value
    assert "Failed to import chat service module" in str(err)
    assert err.context["service_type"] == SERVICE_TYPE
    assert "services.chat_services.nonexistent.service" in err.context["module_name"]
