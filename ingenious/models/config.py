"""
Compatibility layer for configuration imports.

The legacy YAML configuration system exposed several models from
``ingenious.models.config``.  The project now uses Pydantic Settings for
configuration, so this module simply re-exports the new settings models to
preserve backwards-compatible import paths while avoiding the YAML loaders.
"""

from __future__ import annotations

from typing import TypeAlias

from ingenious.config.main_settings import IngeniousSettings
from ingenious.config.models import (
    AzureSearchSettings,
    AzureSqlSettings,
    ChatHistorySettings,
    ChatServiceSettings,
    CosmosSettings,
    FileStorageContainerSettings,
    FileStorageSettings,
    LocalSqlSettings,
    LoggingSettings,
    ModelSettings,
    ReceiverSettings,
    ToolServiceSettings,
    WebAuthenticationSettings,
    WebSettings,
)

Config: TypeAlias = IngeniousSettings
ModelConfig: TypeAlias = ModelSettings
ChatHistoryConfig: TypeAlias = ChatHistorySettings
ChatServiceConfig: TypeAlias = ChatServiceSettings
ToolServiceConfig: TypeAlias = ToolServiceSettings
LoggingConfig: TypeAlias = LoggingSettings
AzureSearchConfig: TypeAlias = AzureSearchSettings
AzureSqlConfig: TypeAlias = AzureSqlSettings
CosmosConfig: TypeAlias = CosmosSettings
ReceiverConfig: TypeAlias = ReceiverSettings
WebConfig: TypeAlias = WebSettings
WebAuthConfig: TypeAlias = WebAuthenticationSettings
LocaldbConfig: TypeAlias = LocalSqlSettings
FileStorageContainer: TypeAlias = FileStorageContainerSettings
FileStorage: TypeAlias = FileStorageSettings

__all__ = [
    "Config",
    "ModelConfig",
    "ChatHistoryConfig",
    "ChatServiceConfig",
    "ToolServiceConfig",
    "LoggingConfig",
    "AzureSearchConfig",
    "AzureSqlConfig",
    "CosmosConfig",
    "ReceiverConfig",
    "WebConfig",
    "WebAuthConfig",
    "LocaldbConfig",
    "FileStorageContainer",
    "FileStorage",
]
