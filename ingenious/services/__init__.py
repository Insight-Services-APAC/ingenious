# services/__init__.py
"""
Ingenious Services Package.

This package contains all service implementations including chat services,
dependency injection, and various business logic components.
"""

# Explicit imports for better IDE support - avoid dependencies to prevent circular imports
import importlib
import sys
from typing import Any

from . import chat_service

_LAZY_MODULES = {
    "fastapi_dependencies",
    "auth_dependencies",
}


def __getattr__(name: str) -> Any:
    """Lazily expose selected service modules to maintain backward compatibility."""
    if name in _LAZY_MODULES:
        module = importlib.import_module(f".{name}", __name__)
        setattr(sys.modules[__name__], name, module)
        return module
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __dir__() -> list[str]:
    """Include lazy modules in dir() output for better discoverability."""
    return sorted(list(globals().keys()) + list(_LAZY_MODULES))


__all__ = ["chat_service", *_LAZY_MODULES]
