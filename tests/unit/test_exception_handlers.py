"""Tests for RFC 7807 exception handlers.

This module tests the global exception handlers and RFC 7807 Problem Details
responses to ensure proper error handling across the application.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ingenious.errors import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    DatabaseError,
    RateLimitError,
    RequestValidationError,
    ResourceError,
    ServiceError,
    WorkflowNotFoundError,
)
from ingenious.errors.content_filter_error import ContentFilterError
from ingenious.errors.token_limit_exceeded_error import TokenLimitExceededError
from ingenious.main.exception_handlers import ExceptionHandlers
from ingenious.models.problem_details import ProblemDetail


@pytest.fixture
def mock_request():
    """Create a mock FastAPI request."""
    request = MagicMock(spec=Request)
    request.url.path = "/api/v1/chat"
    request.method = "POST"
    return request


@pytest.fixture
def app():
    """Create a test FastAPI app."""
    test_app = FastAPI()
    ExceptionHandlers.register_handlers(test_app)
    return test_app


@pytest.mark.unit
class TestExceptionHandlers:
    """Test the exception handlers."""

    @pytest.mark.asyncio
    async def test_ingenious_error_returns_rfc7807_format(self, mock_request):
        """Test that IngeniousError returns RFC 7807 Problem Details format."""
        error = RequestValidationError(
            "Validation failed",
            user_message="Invalid request data",
            recovery_suggestion="Check the API documentation",
        )

        response = await ExceptionHandlers.generic_exception_handler(mock_request, error)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 422
        
        content = response.body.decode()
        assert "type" in content
        assert "title" in content
        assert "status" in content
        assert "detail" in content
        assert "instance" in content
        assert "correlation_id" in content
        assert "timestamp" in content

    @pytest.mark.asyncio
    async def test_content_filter_error_returns_406(self, mock_request):
        """Test that ContentFilterError returns 406 status code."""
        error = ContentFilterError()

        response = await ExceptionHandlers.generic_exception_handler(mock_request, error)

        assert response.status_code == 406

    @pytest.mark.asyncio
    async def test_token_limit_exceeded_returns_413(self, mock_request):
        """Test that TokenLimitExceededError returns 413 status code."""
        error = TokenLimitExceededError(
            max_context_length=4096,
            requested_tokens=5000,
        )

        response = await ExceptionHandlers.generic_exception_handler(mock_request, error)

        assert response.status_code == 413

    @pytest.mark.asyncio
    async def test_authentication_error_returns_401(self, mock_request):
        """Test that AuthenticationError returns 401 status code."""
        error = AuthenticationError("Invalid credentials")

        response = await ExceptionHandlers.generic_exception_handler(mock_request, error)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_authorization_error_returns_403(self, mock_request):
        """Test that AuthorizationError returns 403 status code."""
        error = AuthorizationError("Access denied")

        response = await ExceptionHandlers.generic_exception_handler(mock_request, error)

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_workflow_not_found_returns_404(self, mock_request):
        """Test that WorkflowNotFoundError returns 404 status code."""
        error = WorkflowNotFoundError("Workflow not found")

        response = await ExceptionHandlers.generic_exception_handler(mock_request, error)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_rate_limit_error_returns_429(self, mock_request):
        """Test that RateLimitError returns 429 status code."""
        error = RateLimitError("Rate limit exceeded")

        response = await ExceptionHandlers.generic_exception_handler(mock_request, error)

        assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_database_error_returns_503(self, mock_request):
        """Test that DatabaseError returns 503 status code."""
        error = DatabaseError("Database connection failed")

        response = await ExceptionHandlers.generic_exception_handler(mock_request, error)

        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_service_error_returns_502(self, mock_request):
        """Test that ServiceError returns 502 status code."""
        error = ServiceError("External service unavailable")

        response = await ExceptionHandlers.generic_exception_handler(mock_request, error)

        assert response.status_code == 502

    @pytest.mark.asyncio
    async def test_generic_exception_returns_500(self, mock_request):
        """Test that generic Exception returns 500 status code."""
        error = ValueError("Unexpected error")

        response = await ExceptionHandlers.generic_exception_handler(mock_request, error)

        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_correlation_id_included_in_response(self, mock_request):
        """Test that correlation_id is included in error response."""
        error = RequestValidationError(
            "Validation failed",
            user_message="Invalid request data",
        )

        response = await ExceptionHandlers.generic_exception_handler(mock_request, error)

        content = response.body.decode()
        assert "correlation_id" in content
        assert error.context.correlation_id in content

    @pytest.mark.asyncio
    async def test_instance_path_included_in_response(self, mock_request):
        """Test that instance path is included in error response."""
        error = RequestValidationError(
            "Validation failed",
            user_message="Invalid request data",
        )

        response = await ExceptionHandlers.generic_exception_handler(mock_request, error)

        content = response.body.decode()
        assert "instance" in content
        assert "/api/v1/chat" in content

    @pytest.mark.asyncio
    async def test_user_message_not_internal_error(self, mock_request):
        """Test that user_message is returned instead of internal error details."""
        error = RequestValidationError(
            "Internal validation failed with database connection error",
            user_message="Invalid request data",
        )

        response = await ExceptionHandlers.generic_exception_handler(mock_request, error)

        content = response.body.decode()
        assert "Invalid request data" in content
        assert "database connection error" not in content

    @pytest.mark.asyncio
    async def test_recovery_suggestion_included(self, mock_request):
        """Test that recovery_suggestion is included in error response."""
        error = RequestValidationError(
            "Validation failed",
            user_message="Invalid request data",
            recovery_suggestion="Check the API documentation",
        )

        response = await ExceptionHandlers.generic_exception_handler(mock_request, error)

        content = response.body.decode()
        assert "recovery_suggestion" in content
        assert "Check the API documentation" in content

    @pytest.mark.asyncio
    async def test_recoverable_flag_included(self, mock_request):
        """Test that recoverable flag is included in error response."""
        error = RequestValidationError(
            "Validation failed",
            user_message="Invalid request data",
            recoverable=True,
        )

        response = await ExceptionHandlers.generic_exception_handler(mock_request, error)

        content = response.body.decode()
        assert "recoverable" in content

    @pytest.mark.asyncio
    async def test_rate_limit_headers_added(self, mock_request):
        """Test that rate limit headers are added for RateLimitError."""
        error = RateLimitError("Rate limit exceeded")
        error.retry_after = 60

        response = await ExceptionHandlers.generic_exception_handler(mock_request, error)

        assert "Retry-After" in response.headers
        assert response.headers["Retry-After"] == "60"
        assert "X-RateLimit-Reset" in response.headers

    @pytest.mark.asyncio
    async def test_configuration_error_returns_400(self, mock_request):
        """Test that ConfigurationError returns 400 status code."""
        error = ConfigurationError("Invalid configuration")

        response = await ExceptionHandlers.generic_exception_handler(mock_request, error)

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_resource_error_returns_404(self, mock_request):
        """Test that ResourceError returns 404 status code."""
        error = ResourceError("Resource not found")

        response = await ExceptionHandlers.generic_exception_handler(mock_request, error)

        assert response.status_code == 404


@pytest.mark.unit
class TestProblemDetailModel:
    """Test the RFC 7807 ProblemDetail model."""

    def test_problem_detail_creation(self):
        """Test creating a ProblemDetail instance."""
        problem = ProblemDetail(
            type="https://docs.ingenious.dev/errors/VALIDATION_ERROR",
            title="ValidationError",
            status=400,
            detail="conversation_flow is required",
            instance="/api/v1/chat",
            correlation_id="abc123",
            recoverable=True,
            recovery_suggestion="Provide the conversation_flow field",
        )

        assert problem.type == "https://docs.ingenious.dev/errors/VALIDATION_ERROR"
        assert problem.title == "ValidationError"
        assert problem.status == 400
        assert problem.detail == "conversation_flow is required"
        assert problem.instance == "/api/v1/chat"
        assert problem.correlation_id == "abc123"
        assert problem.recoverable is True
        assert problem.recovery_suggestion == "Provide the conversation_flow field"
        assert problem.timestamp is not None

    def test_problem_detail_serialization(self):
        """Test serializing ProblemDetail to dict."""
        problem = ProblemDetail(
            type="https://docs.ingenious.dev/errors/VALIDATION_ERROR",
            title="ValidationError",
            status=400,
            detail="conversation_flow is required",
        )

        data = problem.model_dump()

        assert "type" in data
        assert "title" in data
        assert "status" in data
        assert "detail" in data
        assert "timestamp" in data

    def test_problem_detail_exclude_none(self):
        """Test that None values are excluded when serializing."""
        problem = ProblemDetail(
            type="https://docs.ingenious.dev/errors/VALIDATION_ERROR",
            title="ValidationError",
            status=400,
        )

        data = problem.model_dump(exclude_none=True)

        assert "type" in data
        assert "title" in data
        assert "status" in data
        assert "detail" not in data
        assert "instance" not in data
        assert "correlation_id" not in data

    def test_problem_detail_timestamp_auto_generated(self):
        """Test that timestamp is automatically generated."""
        problem = ProblemDetail(
            type="https://docs.ingenious.dev/errors/VALIDATION_ERROR",
            title="ValidationError",
            status=400,
        )

        assert problem.timestamp is not None
        assert isinstance(problem.timestamp, str)
        # Verify ISO 8601 format
        assert "T" in problem.timestamp

    def test_problem_detail_status_validation(self):
        """Test that status code must be between 400 and 599."""
        # Valid status codes
        problem = ProblemDetail(
            type="https://docs.ingenious.dev/errors/VALIDATION_ERROR",
            title="ValidationError",
            status=400,
        )
        assert problem.status == 400

        problem = ProblemDetail(
            type="https://docs.ingenious.dev/errors/INTERNAL_ERROR",
            title="InternalError",
            status=500,
        )
        assert problem.status == 500

        # Invalid status code should raise validation error
        with pytest.raises(Exception):  # Pydantic validation error
            ProblemDetail(
                type="https://docs.ingenious.dev/errors/INVALID",
                title="Invalid",
                status=200,  # Not an error status
            )
