import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import HTTPException, status
from jose import JWTError, jwt

from ingenious.core.structured_logging import get_logger

logger = get_logger(__name__)


# Get configuration with fallbacks
def _get_jwt_config():
    """Get JWT configuration from settings or environment variables."""
    try:
        from ingenious.config.config import get_config

        config = get_config()
        auth_config = config.web_configuration.authentication

        secret_key = (
            auth_config.jwt_secret_key
            or os.getenv("INGENIOUS_JWT_SECRET_KEY")
            or os.getenv("JWT_SECRET_KEY")
            or "your-secret-key-change-this-in-production"
        )

        algorithm = (
            auth_config.jwt_algorithm or os.getenv("INGENIOUS_JWT_ALGORITHM") or "HS256"
        )

        access_token_expire = (
            auth_config.jwt_access_token_expire_minutes
            or int(os.getenv("INGENIOUS_JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "0"))
            or int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "0"))
            or 1440
        )

        refresh_token_expire = (
            auth_config.jwt_refresh_token_expire_days
            or int(os.getenv("INGENIOUS_JWT_REFRESH_TOKEN_EXPIRE_DAYS", "0"))
            or int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "0"))
            or 7
        )

        return secret_key, algorithm, access_token_expire, refresh_token_expire
    except Exception:
        # Fallback if config is not available
        return (
            os.getenv("INGENIOUS_JWT_SECRET_KEY")
            or os.getenv("JWT_SECRET_KEY")
            or "your-secret-key-change-this-in-production",
            os.getenv("INGENIOUS_JWT_ALGORITHM") or "HS256",
            int(os.getenv("INGENIOUS_JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "1440")),
            int(os.getenv("INGENIOUS_JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7")),
        )


SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS = (
    _get_jwt_config()
)


def create_access_token(
    data: Dict[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return str(encoded_jwt)


def create_refresh_token(data: Dict[str, Any]) -> str:
    """Create a JWT refresh token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return str(encoded_jwt)


def verify_token(token: str, token_type: str = "access") -> Dict[str, Any]:
    """Verify and decode a JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # Check if token type matches expected type
        if payload.get("type") != token_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token type. Expected {token_type}",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check if token has expired
        exp = payload.get("exp")
        if exp is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing expiration",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if datetime.utcnow().timestamp() > exp:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return dict(payload)

    except JWTError as e:
        logger.debug("JWT verification failed", error=str(e), token_type=token_type)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_username_from_token(token: str) -> str:
    """Extract username from a valid JWT token"""
    payload = verify_token(token)
    username = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return str(username)
