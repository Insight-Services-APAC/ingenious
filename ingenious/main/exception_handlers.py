"""Exception handlers for the FastAPI application.

This module contains exception handlers for proper error responses
and logging of exceptions across the application. Errors are returned
in RFC 7807 Problem Details format for standardization.
"""

import os
import time
from typing import TYPE_CHECKING

from dotenv import load_dotenv
from fastapi import Request
from fastapi.exceptions import RequestValidationError as FastAPIValidationError
from fastapi.responses import JSONResponse

from ingenious.core.structured_logging import get_logger
from ingenious.errors import (
    APIError,
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    DatabaseError,
    IngeniousError,
    RateLimitError,
    RequestValidationError,
    ResourceError,
    ServiceError,
    WorkflowNotFoundError,
    handle_exception,
)
from ingenious.errors.content_filter_error import ContentFilterError
from ingenious.errors.token_limit_exceeded_error import TokenLimitExceededError
from ingenious.models.problem_details import ProblemDetail

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger(__name__)


class ExceptionHandlers:
    """Collection of exception handlers for FastAPI application."""

    @staticmethod
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle generic exceptions with RFC 7807 Problem Details responses.

        Args:
            request: FastAPI request object
            exc: Exception that was raised

        Returns:
            JSONResponse with RFC 7807 Problem Details format and appropriate status code
        """
        if os.environ.get("LOADENV") == "True":
            load_dotenv()

        # Handle Ingenious errors with proper status codes and user messages
        if isinstance(exc, IngeniousError):
            status_code = ExceptionHandlers._get_status_code_for_error(exc)

            logger.error(
                "Ingenious error in API",
                error_type=exc.__class__.__name__,
                error_code=exc.error_code,
                category=exc.category.value,
                severity=exc.severity.value,
                correlation_id=exc.context.correlation_id,
                request_path=str(request.url.path),
                request_method=request.method,
                user_id=exc.context.user_id,
                recoverable=exc.recoverable,
                exc_info=True,
            )

            # Create RFC 7807 Problem Details response
            problem = ProblemDetail(
                type=f"https://docs.ingenious.dev/errors/{exc.error_code}",
                title=exc.__class__.__name__,
                status=status_code,
                detail=exc.user_message,
                instance=str(request.url.path),
                correlation_id=exc.context.correlation_id,
                recoverable=exc.recoverable,
                recovery_suggestion=exc.recovery_suggestion,
            )

            response = JSONResponse(
                status_code=status_code,
                content=problem.model_dump(exclude_none=True),
            )

            # Add rate limiting headers if applicable
            if hasattr(exc, "retry_after") and exc.retry_after:
                response.headers["Retry-After"] = str(exc.retry_after)
                response.headers["X-RateLimit-Reset"] = str(int(time.time()) + exc.retry_after)

            return response

        # Convert generic exceptions to Ingenious errors
        else:
            ingenious_error = handle_exception(
                exc,
                operation="api_request",
                component="fastapi",
                request_path=str(request.url.path),
                request_method=request.method,
            )

            logger.error(
                "Unhandled exception converted to IngeniousError",
                error_type=type(exc).__name__,
                error_message=str(exc),
                correlation_id=ingenious_error.context.correlation_id,
                request_path=str(request.url.path),
                request_method=request.method,
                exc_info=True,
            )

            # Create RFC 7807 Problem Details response for generic errors
            problem = ProblemDetail(
                type="https://docs.ingenious.dev/errors/INTERNAL_ERROR",
                title="InternalServerError",
                status=500,
                detail=ingenious_error.user_message,
                instance=str(request.url.path),
                correlation_id=ingenious_error.context.correlation_id,
                recoverable=ingenious_error.recoverable,
                recovery_suggestion=ingenious_error.recovery_suggestion,
            )

            return JSONResponse(
                status_code=500,
                content=problem.model_dump(exclude_none=True),
            )

    @staticmethod
    async def validation_exception_handler(
        request: Request, exc: FastAPIValidationError
    ) -> JSONResponse:
        """Handle FastAPI validation errors with RFC 7807 Problem Details format.

        Args:
            request: FastAPI request object
            exc: FastAPI validation error that was raised

        Returns:
            JSONResponse with RFC 7807 Problem Details format and 422 status code
        """
        # Generate user-friendly error message based on the specific error
        user_message, recovery_suggestion = (
            ExceptionHandlers._generate_user_friendly_validation_message(exc, str(request.url.path))
        )

        # Create structured validation error
        validation_error = RequestValidationError(
            "Request validation failed",
            context={
                "request_path": str(request.url.path),
                "request_method": request.method,
                "validation_errors": exc.errors() if hasattr(exc, "errors") else [],
                "request_body": getattr(exc, "body", None),
            },
            user_message=user_message,
            recovery_suggestion=recovery_suggestion,
        )

        logger.warning(
            "Request validation error",
            error_type="RequestValidationError",
            error_code=validation_error.error_code,
            request_path=str(request.url.path),
            request_method=request.method,
            validation_errors=exc.errors() if hasattr(exc, "errors") else [],
            correlation_id=validation_error.context.correlation_id,
        )

        # Create RFC 7807 Problem Details response
        problem = ProblemDetail(
            type=f"https://docs.ingenious.dev/errors/{validation_error.error_code}",
            title="RequestValidationError",
            status=422,
            detail=validation_error.user_message,
            instance=str(request.url.path),
            correlation_id=validation_error.context.correlation_id,
            recoverable=validation_error.recoverable,
            recovery_suggestion=validation_error.recovery_suggestion,
        )

        return JSONResponse(
            status_code=422,
            content=problem.model_dump(exclude_none=True),
        )

    @staticmethod
    def _generate_user_friendly_validation_message(
        exc: FastAPIValidationError, request_path: str
    ) -> tuple[str, str]:
        """Generate user-friendly error messages for validation errors.

        Args:
            exc: FastAPI validation error
            request_path: Request path where the error occurred

        Returns:
            Tuple of (user_message, recovery_suggestion)
        """
        errors = exc.errors() if hasattr(exc, "errors") else []

        # Handle bike-insights specific JSON validation errors
        if "/api/v1/chat" in request_path:
            for error in errors:
                error_type = error.get("type", "")
                error_msg = error.get("msg", "")
                error_loc = error.get("loc", [])

                # JSON decode errors
                if "json_invalid" in error_type or "JSON decode error" in error_msg:
                    if "Extra data" in str(error.get("ctx", {})):
                        return (
                            "Invalid JSON format detected. This commonly happens when there are extra characters or formatting issues in your JSON data.",
                            'For bike-insights workflow: Use the corrected file creation method from the README. Avoid heredoc if it\'s adding extra EOF lines. Try: printf \'%s\\n\' \'{"user_prompt": "...", "conversation_flow": "bike-insights"}\' > test_file.json',
                        )
                    else:
                        return (
                            "JSON parsing failed. Your request contains malformed JSON.",
                            "Check for: missing quotes, trailing commas, unescaped characters, or extra brackets. For bike-insights, ensure the user_prompt contains properly escaped JSON data.",
                        )

                # Missing required fields
                elif "missing" in error_type:
                    field_name = error_loc[-1] if error_loc else "field"
                    return (
                        f"Required field '{field_name}' is missing from your request.",
                        f"Add the missing '{field_name}' field to your JSON request. For chat requests, ensure both 'user_prompt' and 'conversation_flow' are provided.",
                    )

                # Type validation errors
                elif "type_error" in error_type:
                    field_name = error_loc[-1] if error_loc else "field"
                    return (
                        f"Field '{field_name}' has an incorrect data type.",
                        f"Check that '{field_name}' matches the expected format. For conversation_flow, use a string like 'bike-insights' or 'classification-agent'.",
                    )

        # Handle prompts API validation errors
        elif "/api/v1/prompts/" in request_path:
            for error in errors:
                error_type = error.get("type", "")
                if "missing" in error_type:
                    return (
                        "Missing required content field for prompt update.",
                        "Include a 'content' field in your JSON request body with the new prompt content as a string.",
                    )

        # Generic fallback for other validation errors
        if errors:
            first_error = errors[0]
            error_msg = first_error.get("msg", "")
            error_loc = first_error.get("loc", [])
            field_name = error_loc[-1] if error_loc else "field"

            return (
                f"Validation error in '{field_name}': {error_msg}",
                "Check the API documentation for the correct request format and ensure all required fields are provided.",
            )

        # Final fallback
        return (
            "Invalid request format. Please check your input data.",
            "Verify your JSON structure matches the API requirements and all required fields are present.",
        )

    @staticmethod
    def _get_status_code_for_error(error: IngeniousError) -> int:
        """Map Ingenious errors to appropriate HTTP status codes.

        Args:
            error: Ingenious error instance

        Returns:
            HTTP status code (400-599)
        """
        # Authentication and authorization errors
        if isinstance(error, AuthenticationError):
            return 401
        elif isinstance(error, AuthorizationError):
            return 403

        # Content filter and token limit errors
        elif isinstance(error, ContentFilterError):
            return 406  # Not Acceptable for content filter violations
        elif isinstance(error, TokenLimitExceededError):
            return 413  # Payload Too Large for token limit exceeded

        # Client errors (4xx)
        elif isinstance(error, RequestValidationError):
            return 422  # Unprocessable Entity for validation errors
        elif isinstance(error, ConfigurationError):
            return 400  # Bad Request for configuration issues
        elif isinstance(error, (WorkflowNotFoundError, ResourceError)):
            return 404
        elif isinstance(error, RateLimitError):
            return 429

        # Server errors (5xx)
        elif isinstance(error, DatabaseError):
            return 503  # Service Unavailable for database issues
        elif isinstance(error, ServiceError):
            return 502  # Bad Gateway for service issues
        elif isinstance(error, APIError):
            # Check if it's a client error based on message
            if "timeout" in error.message.lower():
                return 504  # Gateway Timeout
            elif "not found" in error.message.lower():
                return 404
            else:
                return 500

        # Default to internal server error
        else:
            return 500

    @classmethod
    def register_handlers(cls, app: "FastAPI") -> None:
        """Register all exception handlers with the FastAPI app.

        Args:
            app: FastAPI application instance
        """
        app.add_exception_handler(Exception, cls.generic_exception_handler)
        app.add_exception_handler(
            FastAPIValidationError,
            cls.validation_exception_handler,  # type: ignore
        )
