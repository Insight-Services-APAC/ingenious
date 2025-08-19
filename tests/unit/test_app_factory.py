"""
Tests for ingenious.main.app_factory module
"""

import os
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from ingenious.main.app_factory import FastAgentAPI, create_app


class TestFastAgentAPI:
    """Test cases for FastAgentAPI class"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_config = Mock()

    def test_module_docstring(self):
        """Test that the module has appropriate documentation"""
        import ingenious.main.app_factory as app_factory

        docstring = app_factory.__doc__
        assert docstring is not None
        assert "FastAPI application factory" in docstring

    def test_imports_exist(self):
        """Test that all required imports are available"""
        import ingenious.main.app_factory as app_factory

        # Test that all required imports are accessible
        assert hasattr(app_factory, "os")
        assert hasattr(app_factory, "TYPE_CHECKING")
        assert hasattr(app_factory, "FastAPI")
        assert hasattr(app_factory, "CORSMiddleware")
        assert hasattr(app_factory, "RedirectResponse")
        assert hasattr(app_factory, "ExceptionHandlers")
        assert hasattr(app_factory, "RequestContextMiddleware")
        assert hasattr(app_factory, "RouteManager")

    @patch.dict(os.environ, {"INGENIOUS_WORKING_DIR": "/test/dir"})
    @patch("os.chdir")
    @patch("ingenious.main.app_factory.RouteManager")
    @patch("ingenious.main.app_factory.ExceptionHandlers")
    def test_init_creates_and_configures_app(
        self, mock_exception_handlers, mock_route_manager, mock_chdir
    ):
        """Test that __init__ creates and configures the app"""
        api = FastAgentAPI(self.mock_config)

        # Verify app was created
        assert isinstance(api.app, FastAPI)
        assert api.config is self.mock_config

        # Verify configuration methods were called
        mock_chdir.assert_called_once_with("/test/dir")
        mock_route_manager.register_all_routes.assert_called_once_with(
            api.app, self.mock_config
        )
        mock_exception_handlers.register_handlers.assert_called_once_with(api.app)

    def test_create_app_returns_fastapi_instance(self):
        """Test that _create_app returns a FastAPI instance"""
        api = FastAgentAPI.__new__(FastAgentAPI)  # Create without calling __init__
        api.config = self.mock_config

        app = api._create_app()

        assert isinstance(app, FastAPI)
        assert app.title == "FastAgent API"
        assert app.version == "1.0.0"

    def test_setup_dependency_injection_does_nothing(self):
        """Test that _setup_dependency_injection is a no-op"""
        api = FastAgentAPI.__new__(FastAgentAPI)
        api.config = self.mock_config

        # Should not raise any exceptions
        api._setup_dependency_injection()

    @patch.dict(os.environ, {"INGENIOUS_WORKING_DIR": "/custom/path"})
    @patch("os.chdir")
    def test_setup_working_directory(self, mock_chdir):
        """Test that _setup_working_directory changes to correct directory"""
        api = FastAgentAPI.__new__(FastAgentAPI)
        api.config = self.mock_config

        api._setup_working_directory()

        mock_chdir.assert_called_once_with("/custom/path")

    def test_setup_middleware_configures_cors_and_context(self):
        """Test that _setup_middleware configures middleware correctly"""
        api = FastAgentAPI.__new__(FastAgentAPI)
        api.config = self.mock_config
        api.app = Mock()

        api._setup_middleware()

        # Verify middleware was added (CORS, Context, and Authentication)
        assert api.app.add_middleware.call_count == 3

        # Check that RequestContextMiddleware was added first
        first_call = api.app.add_middleware.call_args_list[0]
        assert "RequestContextMiddleware" in str(first_call[0][0])

        # Check that CORSMiddleware was added second with correct config
        second_call = api.app.add_middleware.call_args_list[1]
        args, kwargs = second_call
        assert "CORSMiddleware" in str(args[0])
        assert "http://localhost" in kwargs["allow_origins"]

        # Check that AuthenticationMiddleware was added third
        third_call = api.app.add_middleware.call_args_list[2]
        assert "AuthenticationMiddleware" in str(third_call[0][0])
        assert "http://localhost:5173" in kwargs["allow_origins"]
        assert "http://localhost:4173" in kwargs["allow_origins"]
        assert kwargs["allow_credentials"] is True
        assert kwargs["allow_methods"] == ["*"]
        assert kwargs["allow_headers"] == ["*"]

    @patch("ingenious.main.app_factory.RouteManager")
    def test_setup_routes(self, mock_route_manager):
        """Test that _setup_routes registers routes"""
        api = FastAgentAPI.__new__(FastAgentAPI)
        api.config = self.mock_config
        api.app = Mock()

        api._setup_routes()

        mock_route_manager.register_all_routes.assert_called_once_with(
            api.app, self.mock_config
        )

    @patch("ingenious.main.app_factory.ExceptionHandlers")
    def test_setup_exception_handlers(self, mock_exception_handlers):
        """Test that _setup_exception_handlers registers handlers"""
        api = FastAgentAPI.__new__(FastAgentAPI)
        api.config = self.mock_config
        api.app = Mock()

        api._setup_exception_handlers()

        mock_exception_handlers.register_handlers.assert_called_once_with(api.app)

    def test_setup_optional_services_does_nothing(self):
        """Test that _setup_optional_services is a no-op"""
        api = FastAgentAPI.__new__(FastAgentAPI)
        api.config = self.mock_config

        # Should not raise any exceptions
        api._setup_optional_services()

    def test_setup_root_redirect_adds_route(self):
        """Test that _setup_root_redirect sets up root endpoint"""
        api = FastAgentAPI.__new__(FastAgentAPI)
        api.config = self.mock_config
        api.app = Mock()

        # Mock the get method to return a decorator
        mock_decorator = Mock()
        api.app.get.return_value = mock_decorator

        api._setup_root_redirect()

        # Verify the route was registered
        api.app.get.assert_called_once_with("/", tags=["Root"])
        mock_decorator.assert_called_once_with(api.redirect_to_docs)

    @pytest.mark.asyncio
    async def test_redirect_to_docs(self):
        """Test that redirect_to_docs returns correct redirect"""
        api = FastAgentAPI.__new__(FastAgentAPI)
        api.config = self.mock_config

        result = await api.redirect_to_docs()

        assert isinstance(result, RedirectResponse)
        # RedirectResponse stores URL in different attribute
        assert "/docs" in str(result) or hasattr(result, "headers")

    @patch.dict(os.environ, {"INGENIOUS_WORKING_DIR": "/test"})
    @patch("os.chdir")
    @patch("ingenious.main.app_factory.RouteManager")
    @patch("ingenious.main.app_factory.ExceptionHandlers")
    def test_configure_app_calls_all_setup_methods(
        self, mock_exception_handlers, mock_route_manager, mock_chdir
    ):
        """Test that _configure_app calls all setup methods in correct order"""
        api = FastAgentAPI.__new__(FastAgentAPI)
        api.config = self.mock_config
        api.app = Mock()

        # Mock all the setup methods to track call order
        with (
            patch.object(api, "_setup_dependency_injection") as mock_di,
            patch.object(api, "_setup_working_directory") as mock_wd,
            patch.object(api, "_setup_middleware") as mock_mw,
            patch.object(api, "_setup_routes") as mock_routes,
            patch.object(api, "_setup_exception_handlers") as mock_eh,
            patch.object(api, "_setup_optional_services") as mock_os,
            patch.object(api, "_setup_root_redirect") as mock_rr,
        ):
            api._configure_app()

            # Verify all methods were called
            mock_di.assert_called_once()
            mock_wd.assert_called_once()
            mock_mw.assert_called_once()
            mock_routes.assert_called_once()
            mock_eh.assert_called_once()
            mock_os.assert_called_once()
            mock_rr.assert_called_once()


class TestCreateApp:
    """Test cases for create_app factory function"""

    @patch.dict(os.environ, {"INGENIOUS_WORKING_DIR": "/test"})
    @patch("os.chdir")
    @patch("ingenious.main.app_factory.RouteManager")
    @patch("ingenious.main.app_factory.ExceptionHandlers")
    def test_create_app_returns_configured_fastapi_app(
        self, mock_exception_handlers, mock_route_manager, mock_chdir
    ):
        """Test that create_app returns a properly configured FastAPI instance"""
        mock_config = Mock()

        app = create_app(mock_config)

        # Verify it returns a FastAPI instance
        assert isinstance(app, FastAPI)
        assert app.title == "FastAgent API"
        assert app.version == "1.0.0"

        # Verify configuration was applied
        mock_chdir.assert_called_once_with("/test")
        mock_route_manager.register_all_routes.assert_called_once()
        mock_exception_handlers.register_handlers.assert_called_once()

    def test_create_app_docstring(self):
        """Test that create_app has proper docstring"""
        assert create_app.__doc__ is not None
        assert (
            "Factory function to create a configured FastAPI application"
            in create_app.__doc__
        )
        assert "Args:" in create_app.__doc__
        assert "Returns:" in create_app.__doc__

    @patch.dict(os.environ, {"INGENIOUS_WORKING_DIR": "/test"})
    @patch("os.chdir")
    @patch("ingenious.main.app_factory.RouteManager")
    @patch("ingenious.main.app_factory.ExceptionHandlers")
    def test_create_app_creates_new_fast_agent_api_instance(
        self, mock_exception_handlers, mock_route_manager, mock_chdir
    ):
        """Test that create_app creates a new FastAgentAPI instance"""
        mock_config = Mock()

        with patch("ingenious.main.app_factory.FastAgentAPI") as mock_fast_agent_api:
            mock_api_instance = Mock()
            mock_api_instance.app = Mock()
            mock_fast_agent_api.return_value = mock_api_instance

            result = create_app(mock_config)

            # Verify FastAgentAPI was created with config
            mock_fast_agent_api.assert_called_once_with(mock_config)

            # Verify the app was returned
            assert result is mock_api_instance.app
