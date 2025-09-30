"""
Error handling context managers and utilities
============================================

This module provides context managers and utilities for consistent error
handling throughout the Ingenious system, including:

- Context managers for common operations
- Error recovery strategies
- Correlation ID tracking
- Retry mechanisms with exponential backoff
- Database transaction error handling

Usage Examples:

    # Database operations with auto-retry
    with database_operation("user_creation", max_retries=3):
        user = create_user(data)

    # API operations with correlation tracking
    with api_operation("chat_request") as ctx:
        response = process_chat(request)
        ctx.add_metadata(response_tokens=response.token_count)

    # File operations with proper error mapping
    with file_operation("env_load", "/path/to/.env"):
        load_environment()
"""

from __future__ import annotations

import asyncio
import functools
import random
import time
from contextlib import asynccontextmanager, contextmanager
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    Generator,
    Optional,
    Type,
    TypeVar,
)
from uuid import uuid4

from ingenious.core.structured_logging import get_logger, get_request_id
from ingenious.errors.base import (
    APIError,
    DatabaseConnectionError,
    DatabaseError,
    ErrorContext,
    IngeniousError,
    ResourceError,
    WorkflowError,
    handle_exception,
)

logger = get_logger(__name__)

# Type variables for generic decorators
F = TypeVar("F", bound=Callable[..., Any])


# ─────────────────────────────────────────────────────────────────────────────
# Context Managers for Common Operations
# ─────────────────────────────────────────────────────────────────────────────


class OperationContext:
    """Context for tracking operation state and metadata."""

    def __init__(
        self, operation: str, component: str = "", correlation_id: Optional[str] = None
    ):
        self.operation = operation
        self.component = component
        self.correlation_id = correlation_id or str(uuid4())
        self.start_time = time.time()
        self.metadata: Dict[str, Any] = {}
        self.errors: list[IngeniousError] = []

        # Get request context if available
        request_id = get_request_id()
        if request_id:
            self.correlation_id = request_id

    def add_metadata(self, **kwargs: Any) -> OperationContext:
        """Add metadata to the operation context."""
        self.metadata.update(kwargs)
        return self

    def add_error(self, error: IngeniousError) -> None:
        """Add an error to the operation context."""
        error.with_correlation_id(self.correlation_id)
        self.errors.append(error)

    def get_duration(self) -> float:
        """Get operation duration in seconds."""
        return time.time() - self.start_time


@contextmanager
def operation_context(
    operation: str,
    component: str = "",
    error_class: Type[IngeniousError] = IngeniousError,
    **context_kwargs: Any,
) -> Generator[OperationContext, None, None]:
    """Generic operation context manager with error handling.

    Parameters
    ----------
    operation : str
        Name of the operation being performed
    component : str
        Component performing the operation
    error_class : Type[IngeniousError]
        Error class to use for wrapping exceptions
    **context_kwargs
        Additional context to include in errors

    Yields
    ------
    OperationContext
        Context object for the operation

    Examples
    --------
    >>> with operation_context("user_lookup", "auth_service") as ctx:
    ...     user = find_user(user_id)
    ...     ctx.add_metadata(user_found=user is not None)
    """
    ctx = OperationContext(operation, component)

    try:
        logger.info(
            f"Starting operation: {operation}",
            operation=operation,
            component=component,
            correlation_id=ctx.correlation_id,
            **context_kwargs,
        )

        yield ctx

        logger.info(
            f"Completed operation: {operation}",
            operation=operation,
            component=component,
            correlation_id=ctx.correlation_id,
            duration_seconds=ctx.get_duration(),
            **ctx.metadata,
        )

    except IngeniousError:
        # Re-raise Ingenious errors as-is
        raise

    except Exception as exc:
        # Convert generic exceptions to Ingenious errors
        error_context = ErrorContext(
            operation=operation,
            component=component,
            correlation_id=ctx.correlation_id,
            **context_kwargs,
        ).with_stack_trace()

        error = error_class(
            message=f"Operation '{operation}' failed: {str(exc)}",
            context=error_context,
            cause=exc,
        )

        logger.error(
            f"Operation failed: {operation}",
            operation=operation,
            component=component,
            correlation_id=ctx.correlation_id,
            duration_seconds=ctx.get_duration(),
            error_type=type(exc).__name__,
            error_message=str(exc),
            **ctx.metadata,
        )

        raise error from exc


@contextmanager
def database_operation(
    operation: str,
    table: Optional[str] = None,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> Generator[OperationContext, None, None]:
    """Context manager for database operations with retry logic.

    Parameters
    ----------
    operation : str
        Database operation being performed
    table : str, optional
        Database table being accessed
    max_retries : int
        Maximum number of retry attempts
    retry_delay : float
        Delay between retries in seconds

    Examples
    --------
    >>> with database_operation("user_create", "users", max_retries=3):
    ...     user = db.create_user(user_data)
    """
    context_kwargs = {}
    if table:
        context_kwargs["table"] = table

    for attempt in range(max_retries + 1):
        try:
            with operation_context(
                operation=operation,
                component="database",
                error_class=DatabaseError,
                attempt=attempt + 1,
                max_retries=max_retries,
                **context_kwargs,
            ) as ctx:
                yield ctx
                return  # Success, exit retry loop

        except DatabaseConnectionError as exc:
            if attempt >= max_retries:
                raise

            logger.warning(
                f"Database connection failed, retrying ({attempt + 1}/{max_retries})",
                operation=operation,
                attempt=attempt + 1,
                max_retries=max_retries,
                retry_delay=retry_delay,
                error=str(exc),
            )

            time.sleep(retry_delay * (2**attempt))  # Exponential backoff

        except DatabaseError:
            # Don't retry non-connection database errors
            raise


@contextmanager
def api_operation(
    operation: str, endpoint: Optional[str] = None, method: Optional[str] = None
) -> Generator[OperationContext, None, None]:
    """Context manager for API operations.

    Parameters
    ----------
    operation : str
        API operation being performed
    endpoint : str, optional
        API endpoint being called
    method : str, optional
        HTTP method being used

    Examples
    --------
    >>> with api_operation("chat_request", "/api/v1/chat", "POST") as ctx:
    ...     response = process_chat_request(request)
    ...     ctx.add_metadata(response_tokens=response.token_count)
    """
    context_kwargs = {}
    if endpoint:
        context_kwargs["endpoint"] = endpoint
    if method:
        context_kwargs["method"] = method

    with operation_context(
        operation=operation, component="api", error_class=APIError, **context_kwargs
    ) as ctx:
        yield ctx


@contextmanager
def file_operation(
    operation: str, file_path: str, required: bool = True
) -> Generator[OperationContext, None, None]:
    """Context manager for file operations.

    Parameters
    ----------
    operation : str
        File operation being performed
    file_path : str
        Path to the file being accessed
    required : bool
        Whether the file is required to exist

    Examples
    --------
    >>> with file_operation("env_load", "/path/to/.env"):
    ...     load_environment()
    """
    try:
        with operation_context(
            operation=operation,
            component="filesystem",
            error_class=ResourceError,
            file_path=file_path,
            required=required,
        ) as ctx:
            yield ctx

    except (FileNotFoundError, PermissionError, OSError) as exc:
        # Map filesystem errors to appropriate Ingenious errors
        error_context = (
            ErrorContext(operation=operation, component="filesystem")
            .with_stack_trace()
            .add_metadata(file_path=file_path)
        )

        if isinstance(exc, FileNotFoundError):
            error = ResourceError(
                message=f"File not found: {file_path}",
                context=error_context,
                cause=exc,
                recoverable=not required,
            )
        elif isinstance(exc, PermissionError):
            error = ResourceError(
                message=f"Permission denied accessing file: {file_path}",
                context=error_context,
                cause=exc,
                recoverable=False,
            )
        else:
            error = ResourceError(
                message=f"File operation failed: {str(exc)}",
                context=error_context,
                cause=exc,
            )

        raise error from exc


@contextmanager
def workflow_operation(
    workflow_name: str, operation: str, step: Optional[str] = None
) -> Generator[OperationContext, None, None]:
    """Context manager for workflow operations.

    Parameters
    ----------
    workflow_name : str
        Name of the workflow being executed
    operation : str
        Specific operation within the workflow
    step : str, optional
        Current step in the workflow

    Examples
    --------
    >>> with workflow_operation("chat_flow", "process_message", "validation"):
    ...     validate_message(message)
    """
    context_kwargs = {"workflow_name": workflow_name}
    if step:
        context_kwargs["workflow_step"] = step

    with operation_context(
        operation=operation,
        component="workflow",
        error_class=WorkflowError,
        **context_kwargs,
    ) as ctx:
        yield ctx


# ─────────────────────────────────────────────────────────────────────────────
# Async Context Managers
# ─────────────────────────────────────────────────────────────────────────────


@asynccontextmanager
async def async_operation_context(
    operation: str,
    component: str = "",
    error_class: Type[IngeniousError] = IngeniousError,
    **context_kwargs: Any,
) -> AsyncGenerator[OperationContext, None]:
    """Async version of operation_context."""
    ctx = OperationContext(operation, component)

    try:
        logger.info(
            f"Starting async operation: {operation}",
            operation=operation,
            component=component,
            correlation_id=ctx.correlation_id,
            **context_kwargs,
        )

        yield ctx

        logger.info(
            f"Completed async operation: {operation}",
            operation=operation,
            component=component,
            correlation_id=ctx.correlation_id,
            duration_seconds=ctx.get_duration(),
            **ctx.metadata,
        )

    except IngeniousError:
        raise

    except Exception as exc:
        error_context = ErrorContext(
            operation=operation,
            component=component,
            correlation_id=ctx.correlation_id,
            **context_kwargs,
        ).with_stack_trace()

        error = error_class(
            message=f"Async operation '{operation}' failed: {str(exc)}",
            context=error_context,
            cause=exc,
        )

        logger.error(
            f"Async operation failed: {operation}",
            operation=operation,
            component=component,
            correlation_id=ctx.correlation_id,
            duration_seconds=ctx.get_duration(),
            error_type=type(exc).__name__,
            error_message=str(exc),
            **ctx.metadata,
        )

        raise error from exc


# ─────────────────────────────────────────────────────────────────────────────
# Retry Decorators
# ─────────────────────────────────────────────────────────────────────────────


def retry_on_error(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: tuple[Type[Exception], ...] = (IngeniousError,),
    only_recoverable: bool = True,
) -> Callable[[F], F]:
    """Decorator for retrying operations on error.

    Parameters
    ----------
    max_retries : int
        Maximum number of retry attempts
    base_delay : float
        Initial delay between retries
    max_delay : float
        Maximum delay between retries
    exponential_base : float
        Base for exponential backoff
    jitter : bool
        Whether to add random jitter to delays
    exceptions : tuple
        Exception types that should trigger retries
    only_recoverable : bool
        Only retry recoverable IngeniousError instances

    Examples
    --------
    >>> @retry_on_error(max_retries=3, base_delay=1.0)
    >>> def fetch_external_data():
    ...     # This will retry up to 3 times on IngeniousError
    ...     return api_client.get_data()
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)

                except exceptions as exc:
                    last_exception = exc

                    # Check if we should retry this exception
                    should_retry = True
                    if isinstance(exc, IngeniousError) and only_recoverable:
                        should_retry = exc.recoverable

                    # Don't retry on the last attempt or non-recoverable errors
                    if attempt >= max_retries or not should_retry:
                        if isinstance(exc, IngeniousError):
                            exc.with_context(
                                retry_count=attempt,
                                max_retries=max_retries,
                                final_attempt=True,
                            )
                        raise exc

                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (exponential_base**attempt), max_delay)

                    # Add jitter to prevent thundering herd
                    if jitter:
                        delay *= 0.5 + random.random() * 0.5

                    # Log retry attempt
                    logger.warning(
                        f"Retrying {func.__name__} after error",
                        function_name=func.__name__,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        delay_seconds=delay,
                        exception_type=exc.__class__.__name__,
                        error_message=str(exc),
                    )

                    # Update context with retry information
                    if isinstance(exc, IngeniousError):
                        exc.with_context(
                            retry_count=attempt + 1,
                            max_retries=max_retries,
                            next_delay_seconds=delay,
                        )

                    time.sleep(delay)

            # This should never be reached, but just in case
            if last_exception:
                raise last_exception
            else:
                raise IngeniousError(
                    "Retry loop completed without success or exception"
                )

        return wrapper  # type: ignore

    return decorator


def async_retry_on_error(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: tuple[Type[Exception], ...] = (IngeniousError,),
    only_recoverable: bool = True,
) -> Callable[[F], F]:
    """Async version of retry_on_error decorator."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)

                except exceptions as exc:
                    last_exception = exc

                    should_retry = True
                    if isinstance(exc, IngeniousError) and only_recoverable:
                        should_retry = exc.recoverable

                    if attempt >= max_retries or not should_retry:
                        if isinstance(exc, IngeniousError):
                            exc.with_context(
                                retry_count=attempt,
                                max_retries=max_retries,
                                final_attempt=True,
                            )
                        raise exc

                    delay = min(base_delay * (exponential_base**attempt), max_delay)

                    if jitter:
                        delay *= 0.5 + random.random() * 0.5

                    logger.warning(
                        f"Retrying async {func.__name__} after error",
                        function_name=func.__name__,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        delay_seconds=delay,
                        exception_type=exc.__class__.__name__,
                        error_message=str(exc),
                    )

                    if isinstance(exc, IngeniousError):
                        exc.with_context(
                            retry_count=attempt + 1,
                            max_retries=max_retries,
                            next_delay_seconds=delay,
                        )

                    await asyncio.sleep(delay)

            if last_exception:
                raise last_exception
            else:
                raise IngeniousError(
                    "Async retry loop completed without success or exception"
                )

        return wrapper  # type: ignore

    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# Error Recovery Strategies
# ─────────────────────────────────────────────────────────────────────────────


class RecoveryStrategy:
    """Base class for error recovery strategies."""

    def can_recover(self, error: IngeniousError) -> bool:
        """Check if this strategy can recover from the given error."""
        raise NotImplementedError

    def recover(self, error: IngeniousError, *args: Any, **kwargs: Any) -> Any:
        """Attempt to recover from the error."""
        raise NotImplementedError


class FallbackRecoveryStrategy(RecoveryStrategy):
    """Recovery strategy that tries fallback operations."""

    def __init__(self, fallback_functions: list[Callable[..., Any]]):
        self.fallback_functions = fallback_functions

    def can_recover(self, error: IngeniousError) -> bool:
        """Check if fallback recovery is applicable."""
        return error.recoverable and len(self.fallback_functions) > 0

    def recover(self, error: IngeniousError, *args: Any, **kwargs: Any) -> Any:
        """Try fallback functions in order."""
        for i, fallback_func in enumerate(self.fallback_functions):
            try:
                logger.info(
                    f"Attempting recovery with fallback function {i + 1}",
                    fallback_function=fallback_func.__name__,
                    original_error=error.error_code,
                )
                return fallback_func(*args, **kwargs)

            except Exception as fallback_error:
                logger.warning(
                    f"Fallback function {i + 1} also failed",
                    fallback_function=fallback_func.__name__,
                    error=str(fallback_error),
                )
                continue

        # If all fallbacks failed, raise the original error
        raise error


class CircuitBreakerRecoveryStrategy(RecoveryStrategy):
    """Recovery strategy that implements circuit breaker pattern."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: Type[Exception] = IngeniousError,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "closed"  # closed, open, half-open

    def can_recover(self, error: IngeniousError) -> bool:
        """Check if circuit breaker should be applied."""
        return isinstance(error, self.expected_exception)

    def recover(
        self,
        error: IngeniousError,
        operation: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Apply circuit breaker logic."""
        current_time = time.time()

        if self.state == "open":
            if current_time - self.last_failure_time > self.recovery_timeout:
                self.state = "half-open"
                logger.info("Circuit breaker transitioning to half-open state")
            else:
                raise error

        try:
            result = operation(*args, **kwargs)

            # Success - reset circuit breaker
            if self.state == "half-open":
                self.state = "closed"
                self.failure_count = 0
                logger.info("Circuit breaker closed after successful recovery")

            return result

        except self.expected_exception as exc:
            self.failure_count += 1
            self.last_failure_time = int(current_time)

            if self.failure_count >= self.failure_threshold:
                self.state = "open"
                logger.warning(
                    f"Circuit breaker opened after {self.failure_count} failures",
                    failure_threshold=self.failure_threshold,
                    recovery_timeout=self.recovery_timeout,
                )

            raise exc


# ─────────────────────────────────────────────────────────────────────────────
# Correlation ID Management
# ─────────────────────────────────────────────────────────────────────────────


def with_correlation_id(correlation_id: Optional[str] = None) -> Callable[[F], F]:
    """Decorator to set correlation ID for an operation.

    Parameters
    ----------
    correlation_id : str, optional
        Correlation ID to use. If None, generates a new one.

    Examples
    --------
    >>> @with_correlation_id()
    >>> def process_request(data):
    ...     # All errors in this function will have the same correlation ID
    ...     return process_data(data)
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cid = correlation_id or str(uuid4())

            # Store correlation ID in thread-local storage or similar
            # This would integrate with your existing request context system

            try:
                return func(*args, **kwargs)
            except IngeniousError as exc:
                exc.with_correlation_id(cid)
                raise
            except Exception as exc:
                # Convert to IngeniousError with correlation ID
                error = handle_exception(
                    exc, operation=func.__name__, component=func.__module__
                )
                error.with_correlation_id(cid)
                raise error from exc

        return wrapper  # type: ignore

    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# Module Exports
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    # Context managers
    "OperationContext",
    "operation_context",
    "database_operation",
    "api_operation",
    "file_operation",
    "workflow_operation",
    "async_operation_context",
    # Retry decorators
    "retry_on_error",
    "async_retry_on_error",
    # Recovery strategies
    "RecoveryStrategy",
    "FallbackRecoveryStrategy",
    "CircuitBreakerRecoveryStrategy",
    # Correlation ID management
    "with_correlation_id",
]
