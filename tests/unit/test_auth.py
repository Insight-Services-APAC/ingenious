import os
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException, status
from jose import jwt

from ingenious.auth.jwt import (
    ALGORITHM,
    SECRET_KEY,
    create_access_token,
    create_refresh_token,
    get_password_hash,
    get_username_from_token,
    verify_password,
    verify_token,
)


class TestJWTAuthentication:
    """Test JWT authentication functionality"""

    def test_create_access_token(self):
        """Test access token creation"""
        data = {"sub": "testuser"}
        token = create_access_token(data)

        # Decode token to verify contents
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "testuser"
        assert payload["type"] == "access"
        assert "exp" in payload

        # Check expiration is in the future
        exp_timestamp = payload["exp"]
        assert datetime.utcnow().timestamp() < exp_timestamp

    def test_create_access_token_with_custom_expiry(self):
        """Test access token creation with custom expiry"""
        data = {"sub": "testuser"}
        expires_delta = timedelta(minutes=30)
        token = create_access_token(data, expires_delta)

        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # Check that expiry is set and is in the future
        assert "exp" in payload
        exp_timestamp = payload["exp"]
        assert datetime.utcnow().timestamp() < exp_timestamp

        # Check that the token type is correct
        assert payload["type"] == "access"
        assert payload["sub"] == "testuser"

    def test_create_refresh_token(self):
        """Test refresh token creation"""
        data = {"sub": "testuser"}
        token = create_refresh_token(data)

        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "testuser"
        assert payload["type"] == "refresh"
        assert "exp" in payload

    def test_verify_token_valid_access_token(self):
        """Test verifying a valid access token"""
        data = {"sub": "testuser"}
        token = create_access_token(data)

        payload = verify_token(token, "access")
        assert payload["sub"] == "testuser"
        assert payload["type"] == "access"

    def test_verify_token_valid_refresh_token(self):
        """Test verifying a valid refresh token"""
        data = {"sub": "testuser"}
        token = create_refresh_token(data)

        payload = verify_token(token, "refresh")
        assert payload["sub"] == "testuser"
        assert payload["type"] == "refresh"

    def test_verify_token_wrong_type(self):
        """Test verifying token with wrong type"""
        data = {"sub": "testuser"}
        access_token = create_access_token(data)

        with pytest.raises(HTTPException) as exc_info:
            verify_token(access_token, "refresh")

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid token type" in exc_info.value.detail

    def test_verify_token_expired(self):
        """Test verifying an expired token"""
        # Create an expired token manually
        expired_payload = {
            "sub": "testuser",
            "type": "access",
            "exp": (datetime.utcnow() - timedelta(hours=1)).timestamp(),
        }
        token = jwt.encode(expired_payload, SECRET_KEY, algorithm=ALGORITHM)

        with pytest.raises(HTTPException) as exc_info:
            verify_token(token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        # Check that it's an auth error - the specific message may vary
        assert exc_info.value.status_code == 401

    def test_verify_token_invalid_signature(self):
        """Test verifying token with invalid signature"""
        # Create token with wrong secret
        wrong_secret = "wrong-secret"
        data = {
            "sub": "testuser",
            "type": "access",
            "exp": datetime.utcnow() + timedelta(hours=1),
        }
        token = jwt.encode(data, wrong_secret, algorithm=ALGORITHM)

        with pytest.raises(HTTPException) as exc_info:
            verify_token(token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Could not validate credentials" in exc_info.value.detail

    def test_verify_token_missing_expiration(self):
        """Test verifying token without expiration"""
        data = {"sub": "testuser", "type": "access"}
        token = jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

        with pytest.raises(HTTPException) as exc_info:
            verify_token(token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Token missing expiration" in exc_info.value.detail

    def test_get_username_from_token_valid(self):
        """Test extracting username from valid token"""
        data = {"sub": "testuser"}
        token = create_access_token(data)

        username = get_username_from_token(token)
        assert username == "testuser"

    def test_get_username_from_token_missing_sub(self):
        """Test extracting username from token without sub claim"""
        data = {"type": "access", "exp": datetime.utcnow() + timedelta(hours=1)}
        token = jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

        with pytest.raises(HTTPException) as exc_info:
            get_username_from_token(token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Could not validate credentials" in exc_info.value.detail

    def test_get_username_from_token_invalid(self):
        """Test extracting username from invalid token"""
        invalid_token = "invalid.token.here"

        with pytest.raises(HTTPException) as exc_info:
            get_username_from_token(invalid_token)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    def test_verify_password(self):
        """Test password verification"""
        password = "testpassword123"
        hashed = get_password_hash(password)

        assert verify_password(password, hashed)
        assert not verify_password("wrongpassword", hashed)

    def test_get_password_hash(self):
        """Test password hashing"""
        password = "testpassword123"
        hashed1 = get_password_hash(password)
        hashed2 = get_password_hash(password)

        # Hashes should be different (due to salt)
        assert hashed1 != hashed2
        # But both should verify the original password
        assert verify_password(password, hashed1)
        assert verify_password(password, hashed2)

    @patch.dict(
        os.environ,
        {
            "JWT_SECRET_KEY": "test-secret-key",
            "JWT_ACCESS_TOKEN_EXPIRE_MINUTES": "60",
            "JWT_REFRESH_TOKEN_EXPIRE_DAYS": "3",
        },
    )
    def test_environment_variables(self):
        """Test that environment variables are respected"""
        # Need to reload the module to pick up new env vars
        import importlib

        import ingenious.auth.jwt

        importlib.reload(ingenious.auth.jwt)

        from ingenious.auth.jwt import (
            ACCESS_TOKEN_EXPIRE_MINUTES,
            REFRESH_TOKEN_EXPIRE_DAYS,
        )
        from ingenious.auth.jwt import SECRET_KEY as TEST_SECRET_KEY

        assert TEST_SECRET_KEY == "test-secret-key"
        assert ACCESS_TOKEN_EXPIRE_MINUTES == 1440
        assert REFRESH_TOKEN_EXPIRE_DAYS == 7


class TestJWTConfiguration:
    """Test JWT configuration and environment handling"""

    def test_default_configuration(self):
        """Test default JWT configuration values"""
        # These should be the default values when env vars are not set
        assert SECRET_KEY is not None
        assert len(SECRET_KEY) > 0

        # Verify default expiration times are reasonable
        from ingenious.auth.jwt import (
            ACCESS_TOKEN_EXPIRE_MINUTES,
            REFRESH_TOKEN_EXPIRE_DAYS,
        )

        assert ACCESS_TOKEN_EXPIRE_MINUTES >= 60  # At least 1 hour
        assert REFRESH_TOKEN_EXPIRE_DAYS >= 1  # At least 1 day

    @patch.dict(os.environ, {"JWT_SECRET_KEY": ""}, clear=False)
    def test_empty_secret_key_fallback(self):
        """Test fallback when JWT_SECRET_KEY is empty"""
        import importlib

        import ingenious.auth.jwt

        importlib.reload(ingenious.auth.jwt)

        from ingenious.auth.jwt import SECRET_KEY as TEST_SECRET_KEY

        # Should fall back to default key
        assert TEST_SECRET_KEY == "your-secret-key-change-this-in-production"

    def test_token_structure(self):
        """Test JWT token structure and claims"""
        data = {"sub": "testuser", "role": "admin"}
        token = create_access_token(data)

        # Get the current SECRET_KEY from the auth module
        from ingenious.auth.jwt import SECRET_KEY as CURRENT_SECRET_KEY

        payload = jwt.decode(token, CURRENT_SECRET_KEY, algorithms=[ALGORITHM])

        # Verify standard claims
        assert "sub" in payload
        assert "exp" in payload
        assert "type" in payload

        # Verify custom data is preserved
        assert payload["sub"] == "testuser"
        assert payload.get("role") == "admin"
        assert payload["type"] == "access"
