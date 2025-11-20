"""FastAPI dependency injection without dependency-injector library."""

from functools import lru_cache
from typing import Any

from fastapi import Depends, Request

from ingenious.common.enums import AuthenticationMethod
from ingenious.config.config import get_config as _get_config
from ingenious.config.settings import IngeniousSettings
from ingenious.core.structured_logging import get_logger
from ingenious.db.chat_history_repository import ChatHistoryRepository
from ingenious.external_services.openai_service import OpenAIService
from ingenious.files.files_repository import FileStorage
from ingenious.models.database_client import DatabaseClientType
from ingenious.services.cache import CacheService, create_cache_service
from ingenious.services.chat_service import ChatService
from ingenious.services.message_feedback_service import MessageFeedbackService

logger = get_logger(__name__)


# Cache the config to avoid reloading
@lru_cache
def get_config() -> IngeniousSettings:
    """Get the application configuration."""
    return _get_config()


# Cache service singleton
_cache_service_instance: CacheService | None = None


def get_cache_service(
    config: IngeniousSettings = Depends(get_config),
) -> CacheService:
    """Get cache service instance (singleton).

    Returns:
        Cache service instance based on configuration.
    """
    global _cache_service_instance

    if _cache_service_instance is None:
        _cache_service_instance = create_cache_service(config.cache)
        logger.info(
            "Cache service initialized",
            enabled=config.cache.enabled,
            backend=config.cache.backend,
        )

    return _cache_service_instance


def get_openai_service(
    config: IngeniousSettings = Depends(get_config),
) -> OpenAIService:
    """Get OpenAI service instance."""
    return OpenAIService(
        azure_endpoint=str(config.models[0].base_url),
        api_key=str(config.models[0].api_key),
        api_version=str(config.models[0].api_version),
        open_ai_model=str(config.models[0].model),
        deployment=str(config.models[0].deployment),
        authentication_method=AuthenticationMethod(config.models[0].authentication_method),
        client_id=str(config.models[0].client_id),
        client_secret=str(config.models[0].client_secret),
        tenant_id=str(config.models[0].tenant_id),
    )


def get_database_type(
    config: IngeniousSettings = Depends(get_config),
) -> DatabaseClientType:
    """Get database type from config."""
    db_type_val = config.chat_history.database_type.lower()
    try:
        return DatabaseClientType(db_type_val)
    except ValueError:
        return DatabaseClientType.SQLITE  # Default to SQLite


def get_chat_history_repository(
    config: IngeniousSettings = Depends(get_config),
    db_type: DatabaseClientType = Depends(get_database_type),
) -> ChatHistoryRepository:
    """Get chat history repository."""
    return ChatHistoryRepository(db_type=db_type, config=config)


def get_chat_service(
    config: IngeniousSettings = Depends(get_config),
    chat_history_repository: ChatHistoryRepository = Depends(get_chat_history_repository),
    openai_service: OpenAIService = Depends(get_openai_service),
) -> ChatService:
    """Get chat service instance."""
    cs_type = config.chat_service.type

    # Create a wrapper that includes the openai_service
    class ConfigWrapper:
        def __init__(self, config: IngeniousSettings, openai_service: OpenAIService):
            self._config = config
            self.openai_service_instance = openai_service

        def __getattr__(self, name: str) -> Any:
            return getattr(self._config, name)

    wrapped_config = ConfigWrapper(config, openai_service)

    return ChatService(
        chat_service_type=cs_type,
        chat_history_repository=chat_history_repository,
        conversation_flow="",  # Will be set per request
        config=wrapped_config,  # type: ignore
    )


def get_message_feedback_service(
    chat_history_repository: ChatHistoryRepository = Depends(get_chat_history_repository),
) -> MessageFeedbackService:
    """Get message feedback service."""
    return MessageFeedbackService(chat_history_repository=chat_history_repository)


def get_file_storage_data(
    config: IngeniousSettings = Depends(get_config),
) -> FileStorage:
    """Get file storage for data."""
    return FileStorage(config=config, Category="data")


def get_file_storage_revisions(
    config: IngeniousSettings = Depends(get_config),
) -> FileStorage:
    """Get file storage for revisions."""
    return FileStorage(config=config, Category="revisions")


def get_conditional_security(
    request: Request, config: IngeniousSettings = Depends(get_config)
) -> str:
    """Get authenticated user - returns 'anonymous' when auth is disabled."""
    # Import here to avoid circular dependency
    from ingenious.services.auth_dependencies import get_auth_user

    return get_auth_user(request, config)
