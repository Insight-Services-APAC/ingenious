"""
DEPRECATED: This module is deprecated in favor of the dependency injection container.

Please use:
- ingenious.services.dependencies for FastAPI dependencies
- ingenious.services.container for the DI container

This module remains for backward compatibility but will be removed in a future version.
"""

import os
import secrets
import warnings
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPBearer
from typing_extensions import Annotated

from ingenious.auth.jwt import get_username_from_token
from ingenious.config.config import get_config as _get_config
from ingenious.config.profile import Profiles
from ingenious.config.settings import IngeniousSettings
from ingenious.core.structured_logging import get_logger
from ingenious.db.chat_history_repository import ChatHistoryRepository
from ingenious.errors import ConfigurationError
from ingenious.external_services.openai_service import OpenAIService
from ingenious.files.files_repository import FileStorage
from ingenious.models.database_client import DatabaseClientType
from ingenious.services.chat_service import ChatService
from ingenious.services.message_feedback_service import MessageFeedbackService

# Issue deprecation warning
warnings.warn(
    "ingenious.dependencies is deprecated. Use ingenious.services.dependencies instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Load environment variables from .env file
load_dotenv()

logger = get_logger(__name__)
security = HTTPBasic()
bearer_security = HTTPBearer()


def get_config() -> IngeniousSettings:
    """Get config dynamically to ensure environment variables are loaded"""
    return _get_config()


def get_profile() -> Profiles:
    """Get profile dynamically to ensure environment variables are loaded"""
    return Profiles(os.getenv("INGENIOUS_PROFILE_PATH", ""))


def get_openai_service() -> OpenAIService:
    config = get_config()
    model = config.models[0]
    return OpenAIService(
        azure_endpoint=str(model.base_url),
        api_key=str(model.api_key) if model.api_key else None,
        api_version=str(model.api_version),
        open_ai_model=str(model.model),
        use_managed_identity=model.use_managed_identity,
    )


def get_chat_history_repository() -> ChatHistoryRepository:
    config = get_config()
    db_type_val = config.chat_history.database_type.lower()
    try:
        db_type = DatabaseClientType(db_type_val)

    except ValueError as e:
        raise ConfigurationError(
            f"Unknown database type: {db_type_val}",
            context={
                "database_type": db_type_val,
                "available_types": [t.value for t in DatabaseClientType],
            },
            cause=e,
            recovery_suggestion="Check the database_type configuration in config.yml",
        ) from e

    chr = ChatHistoryRepository(db_type=db_type, config=config)

    return chr


def get_security_service(
    token: Annotated[str, Depends(bearer_security)] | None = None,
    credentials: Annotated[HTTPBasicCredentials, Depends(security)] | None = None,
) -> str:
    config = get_config()
    if not config.web_configuration.authentication.enable:
        # Authentication is disabled, allow access without checking credentials
        logger.warning(
            "Authentication is disabled. This is not recommended for production use."
        )
        return "anonymous"  # Return something that indicates no auth

    # Try JWT token first (preferred method)
    if token:
        try:
            username = get_username_from_token(token)
            return username
        except HTTPException:
            # JWT token validation failed, fall back to basic auth if available
            pass

    # Fall back to basic auth for backward compatibility
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    current_username_bytes = credentials.username.encode("utf8")
    correct_username_bytes = config.web_configuration.authentication.username.encode(
        "utf-8"
    )
    is_correct_username = secrets.compare_digest(
        current_username_bytes, correct_username_bytes
    )
    current_password_bytes = credentials.password.encode("utf8")
    correct_password_bytes = config.web_configuration.authentication.password.encode(
        "utf-8"
    )
    is_correct_password = secrets.compare_digest(
        current_password_bytes, correct_password_bytes
    )
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.username


def get_security_service_optional(
    credentials: Optional[HTTPBasicCredentials] = None,
) -> Optional[str]:
    """Optional security service that doesn't require credentials when auth is disabled"""
    config = get_config()
    if not config.web_configuration.authentication.enable:
        # Authentication is disabled, don't require credentials
        logger.warning(
            "Authentication is disabled. This is not recommended for production use."
        )
        return None

    # Authentication is enabled, require credentials
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    current_username_bytes = credentials.username.encode("utf8")
    correct_username_bytes = config.web_configuration.authentication.username.encode(
        "utf-8"
    )
    is_correct_username = secrets.compare_digest(
        current_username_bytes, correct_username_bytes
    )
    current_password_bytes = credentials.password.encode("utf8")
    correct_password_bytes = config.web_configuration.authentication.password.encode(
        "utf-8"
    )
    is_correct_password = secrets.compare_digest(
        current_password_bytes, correct_password_bytes
    )
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def get_chat_service(
    chat_history_repository: Annotated[
        ChatHistoryRepository, Depends(get_chat_history_repository)
    ],
    conversation_flow: str = "",
) -> ChatService:
    config = get_config()
    cs_type = config.chat_service.type
    return ChatService(
        chat_service_type=cs_type,
        chat_history_repository=chat_history_repository,
        conversation_flow=conversation_flow,
        config=config,
    )


def get_message_feedback_service(
    chat_history_repository: Annotated[
        ChatHistoryRepository, Depends(get_chat_history_repository)
    ],
) -> MessageFeedbackService:
    return MessageFeedbackService(chat_history_repository)


async def sync_templates() -> None:
    config = get_config()
    if config.file_storage.revisions.storage_type == "local":
        return
    else:
        fs = FileStorage(config)
        working_dir = os.getcwd()
        template_path = os.path.join(working_dir, "ingenious", "templates")
        template_files = await fs.list_files(file_path=template_path)
        for file in template_files:
            file_name = os.path.basename(file)
            file_contents = await fs.read_file(
                file_name=file_name, file_path=template_path
            )
            file_path = os.path.join(working_dir, "ingenious", "templates", file_name)
            with open(file_path, "w") as f:
                f.write(file_contents)


def get_file_storage_data() -> FileStorage:
    config = get_config()
    return FileStorage(config, Category="data")


def get_file_storage_revisions() -> FileStorage:
    config = get_config()
    return FileStorage(config, Category="revisions")


def get_project_config() -> IngeniousSettings:
    return get_config()


def get_auth_user(request: Request) -> str:
    """Get authenticated user - supports both JWT and Basic Auth"""
    config = get_config()

    if not config.web_configuration.authentication.enable:
        # Authentication is disabled, allow access
        logger.warning(
            "Authentication is disabled. This is not recommended for production use."
        )
        return "anonymous"

    # Authentication is enabled, check for JWT token first
    auth_header = request.headers.get("Authorization", "")

    # Try JWT Bearer token first
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]  # Remove "Bearer " prefix
        try:
            username = get_username_from_token(token)
            return username
        except HTTPException:
            # JWT validation failed, continue to basic auth fallback
            pass

    # Fall back to Basic Auth
    if auth_header.startswith("Basic "):
        import base64

        try:
            credentials_str = base64.b64decode(auth_header[6:]).decode("utf-8")
            username, password = credentials_str.split(":", 1)
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication format",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Validate credentials
        current_username_bytes = username.encode("utf8")
        correct_username_bytes = (
            config.web_configuration.authentication.username.encode("utf-8")
        )
        is_correct_username = secrets.compare_digest(
            current_username_bytes, correct_username_bytes
        )

        current_password_bytes = password.encode("utf8")
        correct_password_bytes = (
            config.web_configuration.authentication.password.encode("utf-8")
        )
        is_correct_password = secrets.compare_digest(
            current_password_bytes, correct_password_bytes
        )

        if not (is_correct_username and is_correct_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return username

    # No valid authentication method provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_conditional_security(request: Request) -> str:
    """Get authenticated user - wrapper around get_auth_user for compatibility"""
    return get_auth_user(request)
