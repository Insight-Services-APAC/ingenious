"""Backward compatibility shim for old settings.py imports.

This module re-exports IngeniousSettings from main_settings to maintain
backward compatibility with code that imports from ingenious.config.settings.
"""

from ingenious.config.main_settings import IngeniousSettings
from ingenious.config.models import (
    CacheSettings,
    ChatHistorySettings,
    LoggingSettings,
    ModelSettings,
    WebSettings,
)

__all__ = [
    "IngeniousSettings",
    "CacheSettings",
    "ChatHistorySettings",
    "LoggingSettings",
    "ModelSettings",
    "WebSettings",
]
