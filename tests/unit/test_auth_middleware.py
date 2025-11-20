"""Test authentication middleware."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from ingenious.auth.middleware import AuthenticationMiddleware, setup_auth_middleware
from ingenious.config.settings import IngeniousSettings


class TestAuthenticationMiddleware:
    """Test AuthenticationMiddleware class."""

    @pytest.fixture
    def mock_config(self):
        """Create mock configuration."""
        config = Mock()
        config.web_configuration = Mock()
        config.web_configuration.authentication = Mock()
        config.web_configuration.authentication.enable = True
        config.web_configuration.authentication.enable_global_middleware = True
        return config

    @pytest.fixture
    def mock_app(self):
        """Create mock ASGI app."""
        return MagicMock()

    @pytest.fixture
    def middleware(self, mock_app, mock_config):
        """Create AuthenticationMiddleware instance."""
        return AuthenticationMiddleware(mock_app, mock_config)

    def test_init(self, middleware, mock_config):
        """Test middleware initialization."""
        assert middleware.config == mock_config
        assert "/docs" in middleware.exempt_paths
        assert "/redoc" in middleware.exempt_paths
        assert "/openapi.json" in middleware.exempt_paths
        assert "/api/v1/auth/login" in middleware.exempt_paths
        assert "/api/v1/health" in middleware.exempt_paths

    def test_init_with_custom_exempt_paths(self, mock_app, mock_config):
        """Test middleware initialization with custom exempt paths."""
        custom_paths = ["/custom/path", "/another/path"]
        middleware = AuthenticationMiddleware(mock_app, mock_config, exempt_paths=custom_paths)

        assert middleware.exempt_paths == custom_paths
        assert "/docs" not in middleware.exempt_paths

    @pytest.mark.asyncio
    async def test_dispatch_exempt_path(self, middleware):
        """Test dispatch with exempt path."""
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/docs"

        mock_call_next = AsyncMock()
        mock_response = MagicMock()
        mock_call_next.return_value = mock_response

        response = await middleware.dispatch(mock_request, mock_call_next)

        assert response == mock_response
        mock_call_next.assert_called_once_with(mock_request)

    @pytest.mark.asyncio
    async def test_dispatch_authentication_disabled(self, mock_app, mock_config):
        """Test dispatch when authentication is disabled."""
        mock_config.web_configuration.authentication.enable = False
        middleware = AuthenticationMiddleware(mock_app, mock_config)

        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/v1/protected"

        mock_call_next = AsyncMock()
        mock_response = MagicMock()
        mock_call_next.return_value = mock_response

        response = await middleware.dispatch(mock_request, mock_call_next)

        assert response == mock_response
        mock_call_next.assert_called_once_with(mock_request)

    @pytest.mark.asyncio
    async def test_dispatch_successful_authentication(self, middleware):
        """Test dispatch with successful authentication."""
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/v1/protected"
        mock_request.state = MagicMock()

        mock_call_next = AsyncMock()
        mock_response = MagicMock()
        mock_call_next.return_value = mock_response

        with patch("ingenious.auth.middleware.get_auth_user") as mock_get_auth_user:
            mock_get_auth_user.return_value = "testuser"

            response = await middleware.dispatch(mock_request, mock_call_next)

            assert response == mock_response
            mock_get_auth_user.assert_called_once_with(mock_request, middleware.config)
            assert mock_request.state.username == "testuser"
            mock_call_next.assert_called_once_with(mock_request)

    @pytest.mark.asyncio
    async def test_dispatch_authentication_failure(self, middleware):
        """Test dispatch with authentication failure."""
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/v1/protected"

        mock_call_next = AsyncMock()

        with patch("ingenious.auth.middleware.get_auth_user") as mock_get_auth_user:
            mock_get_auth_user.side_effect = HTTPException(
                status_code=401, detail="Invalid token"
            )

            response = await middleware.dispatch(mock_request, mock_call_next)

            assert isinstance(response, JSONResponse)
            assert response.status_code == 401
            # Verify the response body contains the error detail
            assert b"Invalid token" in response.body

    @pytest.mark.asyncio
    async def test_dispatch_authentication_exception(self, middleware):
        """Test dispatch with unexpected exception during authentication."""
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/v1/protected"

        mock_call_next = AsyncMock()

        with patch("ingenious.auth.middleware.get_auth_user") as mock_get_auth_user:
            mock_get_auth_user.side_effect = Exception("Unexpected error")

            response = await middleware.dispatch(mock_request, mock_call_next)

            assert isinstance(response, JSONResponse)
            assert response.status_code == 500
            assert b"Authentication error" in response.body


class TestSetupAuthMiddleware:
    """Test setup_auth_middleware function."""

    @pytest.fixture
    def mock_app(self):
        """Create mock FastAPI app."""
        return MagicMock(spec=FastAPI)

    @pytest.fixture
    def mock_config(self):
        """Create mock configuration."""
        config = Mock()
        config.web_configuration = Mock()
        config.web_configuration.authentication = Mock()
        config.web_configuration.authentication.enable_global_middleware = True
        return config

    def test_setup_auth_middleware_enabled(self, mock_app, mock_config):
        """Test setting up auth middleware when enabled."""
        setup_auth_middleware(mock_app, mock_config)

        # Verify middleware was added
        mock_app.add_middleware.assert_called_once()
        call_args = mock_app.add_middleware.call_args
        assert call_args[0][0] == AuthenticationMiddleware
        assert call_args[1]["config"] == mock_config

    def test_setup_auth_middleware_disabled(self, mock_app, mock_config):
        """Test setting up auth middleware when disabled."""
        mock_config.web_configuration.authentication.enable_global_middleware = False

        setup_auth_middleware(mock_app, mock_config)

        # Verify middleware was not added
        mock_app.add_middleware.assert_not_called()

    def test_setup_auth_middleware_with_custom_paths(self, mock_app, mock_config):
        """Test setting up auth middleware with custom exempt paths."""
        custom_paths = ["/custom/exempt"]

        setup_auth_middleware(mock_app, mock_config, exempt_paths=custom_paths)

        # Verify middleware was added with custom paths
        mock_app.add_middleware.assert_called_once()
        call_args = mock_app.add_middleware.call_args
        assert call_args[1]["exempt_paths"] == custom_paths
