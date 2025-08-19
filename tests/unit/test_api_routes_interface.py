"""
Tests for ingenious.models.api_routes module
"""

from abc import ABC
from unittest.mock import Mock, patch

import pytest
from fastapi import APIRouter, FastAPI

from ingenious.config.main_settings import IngeniousSettings
from ingenious.models.api_routes import IApiRoutes


class TestIApiRoutes:
    """Test cases for IApiRoutes abstract base class"""

    def test_is_abstract_base_class(self):
        """Test that IApiRoutes is an abstract base class"""
        assert issubclass(IApiRoutes, ABC)

    def test_cannot_instantiate_abstract_class(self):
        """Test that IApiRoutes cannot be instantiated directly"""
        config = Mock(spec=IngeniousSettings)
        app = Mock(spec=FastAPI)

        with pytest.raises(TypeError):
            IApiRoutes(config, app)

    @patch("ingenious.models.api_routes.get_logger")
    def test_concrete_implementation_initialization(self, mock_get_logger):
        """Test that a concrete implementation can be initialized properly"""

        # Create a concrete implementation for testing
        class ConcreteApiRoutes(IApiRoutes):
            def add_custom_routes(self) -> APIRouter:
                return APIRouter()

        # Setup mocks
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger

        # Create test objects
        config = Mock(spec=IngeniousSettings)
        app = Mock(spec=FastAPI)

        # Initialize concrete implementation
        concrete_routes = ConcreteApiRoutes(config, app)

        # Verify initialization
        assert concrete_routes.config is config
        assert concrete_routes.app is app
        assert concrete_routes.logger is mock_logger

        # Verify function calls
        mock_get_logger.assert_called_once_with("ingenious.models.api_routes")

    @patch("ingenious.models.api_routes.get_logger")
    def test_abstract_method_must_be_implemented(self, mock_get_logger):
        """Test that abstract method add_custom_routes must be implemented"""

        # Create a concrete implementation that implements the abstract method
        class ConcreteApiRoutesWithMethod(IApiRoutes):
            def add_custom_routes(self) -> APIRouter:
                router = APIRouter()
                return router

        # Create a concrete implementation that doesn't implement the abstract method
        class ConcreteApiRoutesWithoutMethod(IApiRoutes):
            pass  # Missing add_custom_routes implementation

        config = Mock(spec=IngeniousSettings)
        app = Mock(spec=FastAPI)

        # Should work with proper implementation
        concrete_with_method = ConcreteApiRoutesWithMethod(config, app)
        router = concrete_with_method.add_custom_routes()
        assert isinstance(router, APIRouter)

        # Should fail without proper implementation
        with pytest.raises(TypeError):
            ConcreteApiRoutesWithoutMethod(config, app)

    @patch("ingenious.models.api_routes.get_logger")
    def test_add_custom_routes_return_type(self, mock_get_logger):
        """Test that add_custom_routes returns APIRouter"""

        class ConcreteApiRoutes(IApiRoutes):
            def add_custom_routes(self) -> APIRouter:
                router = APIRouter()
                router.get("/test")(lambda: {"message": "test"})
                return router

        config = Mock(spec=IngeniousSettings)
        app = Mock(spec=FastAPI)

        concrete_routes = ConcreteApiRoutes(config, app)
        router = concrete_routes.add_custom_routes()

        assert isinstance(router, APIRouter)
        # Verify that routes can be added to the router
        assert len(router.routes) > 0

    @patch("ingenious.models.api_routes.get_logger")
    def test_multiple_implementations(self, mock_get_logger):
        """Test that multiple concrete implementations can be created"""

        class ApiRoutesV1(IApiRoutes):
            def add_custom_routes(self) -> APIRouter:
                router = APIRouter()
                router.get("/v1/test")(lambda: {"version": "v1"})
                return router

        class ApiRoutesV2(IApiRoutes):
            def add_custom_routes(self) -> APIRouter:
                router = APIRouter()
                router.get("/v2/test")(lambda: {"version": "v2"})
                return router

        config = Mock(spec=IngeniousSettings)
        app = Mock(spec=FastAPI)

        routes_v1 = ApiRoutesV1(config, app)
        routes_v2 = ApiRoutesV2(config, app)

        router_v1 = routes_v1.add_custom_routes()
        router_v2 = routes_v2.add_custom_routes()

        assert isinstance(router_v1, APIRouter)
        assert isinstance(router_v2, APIRouter)
        assert router_v1 is not router_v2

    @patch("ingenious.models.api_routes.get_logger")
    def test_docstring_exists(self, mock_get_logger):
        """Test that the abstract method has proper documentation"""
        # Check that the abstract method has a docstring
        assert IApiRoutes.add_custom_routes.__doc__ is not None
        assert (
            "Adds custom routes to the FastAPI app instance"
            in IApiRoutes.add_custom_routes.__doc__
        )
        assert "returns the router instance" in IApiRoutes.add_custom_routes.__doc__

    @patch("ingenious.models.api_routes.get_logger")
    def test_inheritance_chain(self, mock_get_logger):
        """Test the inheritance chain and method resolution"""

        class ConcreteApiRoutes(IApiRoutes):
            def add_custom_routes(self) -> APIRouter:
                return APIRouter()

        config = Mock(spec=IngeniousSettings)
        app = Mock(spec=FastAPI)

        concrete_routes = ConcreteApiRoutes(config, app)

        # Test inheritance
        assert isinstance(concrete_routes, IApiRoutes)
        assert isinstance(concrete_routes, ABC)

        # Test method resolution order
        assert hasattr(concrete_routes, "add_custom_routes")
        assert callable(concrete_routes.add_custom_routes)
