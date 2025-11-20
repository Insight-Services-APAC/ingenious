"""FastAPI application factory.

This module contains the factory function for creating and configuring
the FastAPI application with all necessary middleware, routes, and services.
"""

from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from .exception_handlers import ExceptionHandlers
from .middleware import RequestContextMiddleware
from .routing import RouteManager

if TYPE_CHECKING:
    from ingenious.config import IngeniousSettings


class FastAgentAPI:
    """FastAPI application wrapper with initialization and configuration.

    Attributes:
        config: Ingenious configuration settings
        app: FastAPI application instance
    """

    def __init__(self, config: "IngeniousSettings"):
        """Initialize FastAgentAPI with configuration.

        Args:
            config: Ingenious configuration settings
        """
        self.config = config
        self.app = self._create_app()
        self._configure_app()

    def _create_app(self) -> FastAPI:
        """Create the FastAPI application instance.

        Returns:
            FastAPI application instance
        """
        return FastAPI(title="FastAgent API", version="1.0.0")

    def _configure_app(self) -> None:
        """Configure the FastAPI application with middleware, routes, and services."""
        self._setup_dependency_injection()
        self._setup_middleware()
        self._setup_routes()
        self._setup_exception_handlers()
        self._setup_optional_services()
        self._setup_root_redirect()

    def _setup_dependency_injection(self) -> None:
        """Initialize dependency injection - no longer needed with FastAPI DI."""
        # FastAPI handles dependency injection natively
        pass

    def _setup_middleware(self) -> None:
        """Configure middleware stack including CORS and authentication."""
        # Add request context middleware first
        self.app.add_middleware(RequestContextMiddleware)

        # Add CORS middleware
        origins = [
            "http://localhost",
            "http://localhost:5173",
            "http://localhost:4173",
        ]

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Add authentication middleware if configured
        if hasattr(self.config.web_configuration.authentication, "enable_global_middleware"):
            from ingenious.auth.middleware import setup_auth_middleware

            setup_auth_middleware(self.app, self.config)

    def _setup_routes(self) -> None:
        """Register all application routes."""
        RouteManager.register_all_routes(self.app, self.config)

    def _setup_exception_handlers(self) -> None:
        """Configure exception handlers."""
        ExceptionHandlers.register_handlers(self.app)

    def _setup_optional_services(self) -> None:
        """Setup optional services based on configuration."""
        pass

    def _setup_root_redirect(self) -> None:
        """Setup root endpoint redirect."""
        self.app.get("/", tags=["Root"])(self.redirect_to_docs)

    async def redirect_to_docs(self) -> RedirectResponse:
        """Redirect the root endpoint to /docs.

        Returns:
            RedirectResponse to /docs endpoint
        """
        return RedirectResponse(url="/docs")


def create_app(config: "IngeniousSettings") -> FastAPI:
    """Factory function to create a configured FastAPI application.

    Args:
        config: Ingenious configuration settings

    Returns:
        Configured FastAPI application instance
    """
    api = FastAgentAPI(config)
    return api.app
