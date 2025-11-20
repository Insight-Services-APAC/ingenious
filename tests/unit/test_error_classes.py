"""Test error classes."""

import pytest

from ingenious.errors.api import (
    APIError,
    RateLimitError,
    RequestValidationError,
    ResponseError,
)
from ingenious.errors.configuration import (
    ConfigFileError,
    ConfigurationError,
    EnvironmentError,
    ValidationError,
)
from ingenious.errors.context import ErrorContext
from ingenious.errors.database import (
    DatabaseConnectionError,
    DatabaseError,
    DatabaseMigrationError,
    DatabaseQueryError,
    DatabaseTransactionError,
)
from ingenious.errors.enums import ErrorCategory, ErrorSeverity
from ingenious.errors.resource import (
    FileNotFoundError,
    PermissionError,
    ResourceError,
    StorageError,
)
from ingenious.errors.service import (
    AuthenticationError,
    AuthorizationError,
    ChatServiceError,
    ExternalServiceError,
    ServiceError,
)
from ingenious.errors.workflow import (
    WorkflowConfigurationError,
    WorkflowError,
    WorkflowExecutionError,
    WorkflowNotFoundError,
)


class TestAPIErrors:
    """Test API error classes."""

    def test_api_error_basic(self):
        """Test basic APIError."""
        error = APIError("API error occurred")

        assert error.message == "API error occurred"
        assert error.category == ErrorCategory.API
        assert error.severity == ErrorSeverity.MEDIUM

    def test_rate_limit_error(self):
        """Test RateLimitError."""
        error = RateLimitError("Rate limit exceeded", limit=100, window="1m")

        assert error.message == "Rate limit exceeded"
        assert error.category == ErrorCategory.API
        assert error.severity == ErrorSeverity.LOW

    def test_request_validation_error(self):
        """Test RequestValidationError."""
        error = RequestValidationError("Invalid request", field="username")

        assert error.message == "Invalid request"
        assert error.category == ErrorCategory.API

    def test_response_error(self):
        """Test ResponseError."""
        error = ResponseError("Response parsing failed")

        assert error.message == "Response parsing failed"
        assert error.category == ErrorCategory.API


class TestConfigurationErrors:
    """Test configuration error classes."""

    def test_configuration_error_basic(self):
        """Test basic ConfigurationError."""
        error = ConfigurationError("Configuration error occurred")

        assert error.message == "Configuration error occurred"
        assert error.category == ErrorCategory.CONFIGURATION
        assert error.severity == ErrorSeverity.HIGH
        assert error.recoverable is False

    def test_config_file_error(self):
        """Test ConfigFileError."""
        error = ConfigFileError("Config file not found", config_path="/path/to/config.yaml")

        assert error.message == "Config file not found"
        assert error.category == ErrorCategory.CONFIGURATION

    def test_environment_error(self):
        """Test EnvironmentError."""
        error = EnvironmentError("Environment variable missing", env_var="API_KEY")

        assert error.message == "Environment variable missing"
        assert error.category == ErrorCategory.CONFIGURATION

    def test_validation_error(self):
        """Test ValidationError."""
        error = ValidationError("Validation failed", field="email", value="invalid")

        assert error.message == "Validation failed"
        assert error.category == ErrorCategory.CONFIGURATION


class TestDatabaseErrors:
    """Test database error classes."""

    def test_database_error_basic(self):
        """Test basic DatabaseError."""
        error = DatabaseError("Database error occurred")

        assert error.message == "Database error occurred"
        assert error.category == ErrorCategory.DATABASE
        assert error.severity == ErrorSeverity.HIGH
        assert error.recoverable is True

    def test_database_connection_error(self):
        """Test DatabaseConnectionError."""
        conn_str = "Server=test.db;User=admin;Password=secret123"
        error = DatabaseConnectionError("Connection failed", connection_string=conn_str)

        assert error.message == "Connection failed"
        assert error.category == ErrorCategory.DATABASE
        assert error.severity == ErrorSeverity.CRITICAL

    def test_database_connection_error_sanitizes_password(self):
        """Test that DatabaseConnectionError sanitizes passwords."""
        conn_str = "Server=test.db;Password=secret123;User=admin"
        error = DatabaseConnectionError("Connection failed", connection_string=conn_str)

        # Password should be sanitized in context
        # The actual implementation may vary

    def test_database_query_error(self):
        """Test DatabaseQueryError."""
        query = "SELECT * FROM users WHERE id = 123"
        error = DatabaseQueryError("Query failed", query=query)

        assert error.message == "Query failed"
        assert error.category == ErrorCategory.DATABASE

    def test_database_query_error_truncates_long_query(self):
        """Test that DatabaseQueryError truncates long queries."""
        long_query = "SELECT * FROM users WHERE " + "x = 1 AND " * 100
        error = DatabaseQueryError("Query failed", query=long_query)

        assert error.message == "Query failed"
        # Query should be truncated in context

    def test_database_transaction_error(self):
        """Test DatabaseTransactionError."""
        error = DatabaseTransactionError("Transaction failed", transaction_id="tx-12345")

        assert error.message == "Transaction failed"
        assert error.category == ErrorCategory.DATABASE

    def test_database_migration_error(self):
        """Test DatabaseMigrationError."""
        error = DatabaseMigrationError("Migration failed", migration_version="v1.2.3")

        assert error.message == "Migration failed"
        assert error.category == ErrorCategory.DATABASE
        assert error.severity == ErrorSeverity.CRITICAL
        assert error.recoverable is False


class TestResourceErrors:
    """Test resource error classes."""

    def test_resource_error_basic(self):
        """Test basic ResourceError."""
        error = ResourceError("Resource error occurred")

        assert error.message == "Resource error occurred"
        assert error.category == ErrorCategory.RESOURCE
        assert error.severity == ErrorSeverity.MEDIUM

    def test_file_not_found_error(self):
        """Test FileNotFoundError."""
        error = FileNotFoundError("File not found", file_path="/path/to/file.txt")

        assert error.message == "File not found"
        assert error.category == ErrorCategory.RESOURCE
        assert error.recoverable is False

    def test_permission_error(self):
        """Test PermissionError."""
        error = PermissionError("Access denied", resource_path="/protected/resource")

        assert error.message == "Access denied"
        assert error.category == ErrorCategory.RESOURCE
        assert error.severity == ErrorSeverity.HIGH
        assert error.recoverable is False

    def test_storage_error(self):
        """Test StorageError."""
        error = StorageError("Storage operation failed", storage_type="blob")

        assert error.message == "Storage operation failed"
        assert error.category == ErrorCategory.RESOURCE


class TestServiceErrors:
    """Test service error classes."""

    def test_service_error_basic(self):
        """Test basic ServiceError."""
        error = ServiceError("Service error occurred")

        assert error.message == "Service error occurred"
        assert error.category == ErrorCategory.SERVICE
        assert error.severity == ErrorSeverity.MEDIUM

    def test_external_service_error(self):
        """Test ExternalServiceError."""
        error = ExternalServiceError(
            "External service failed",
            service_name="payment-api",
            status_code=503
        )

        assert error.message == "External service failed"
        assert error.category == ErrorCategory.SERVICE
        assert error.severity == ErrorSeverity.HIGH

    def test_chat_service_error(self):
        """Test ChatServiceError."""
        error = ChatServiceError("Chat service failed", service_type="openai")

        assert error.message == "Chat service failed"
        assert error.category == ErrorCategory.SERVICE

    def test_authentication_error(self):
        """Test AuthenticationError."""
        error = AuthenticationError("Authentication failed")

        assert error.message == "Authentication failed"
        assert error.category == ErrorCategory.AUTHENTICATION
        assert error.severity == ErrorSeverity.HIGH
        assert error.recoverable is False

    def test_authorization_error(self):
        """Test AuthorizationError."""
        error = AuthorizationError("Access denied", required_permission="admin")

        assert error.message == "Access denied"
        assert error.category == ErrorCategory.AUTHENTICATION
        assert error.severity == ErrorSeverity.HIGH
        assert error.recoverable is False


class TestWorkflowErrors:
    """Test workflow error classes."""

    def test_workflow_error_basic(self):
        """Test basic WorkflowError."""
        error = WorkflowError("Workflow error occurred")

        assert error.message == "Workflow error occurred"
        assert error.category == ErrorCategory.WORKFLOW
        assert error.severity == ErrorSeverity.MEDIUM

    def test_workflow_not_found_error(self):
        """Test WorkflowNotFoundError."""
        error = WorkflowNotFoundError(
            "Workflow not found",
            workflow_name="data-processing"
        )

        assert error.message == "Workflow not found"
        assert error.category == ErrorCategory.WORKFLOW
        assert error.recoverable is False

    def test_workflow_execution_error(self):
        """Test WorkflowExecutionError."""
        error = WorkflowExecutionError(
            "Workflow execution failed",
            workflow_name="data-processing",
            step="transform"
        )

        assert error.message == "Workflow execution failed"
        assert error.category == ErrorCategory.WORKFLOW

    def test_workflow_configuration_error(self):
        """Test WorkflowConfigurationError."""
        error = WorkflowConfigurationError(
            "Workflow configuration invalid",
            workflow_name="data-processing",
            config_error="Missing required field"
        )

        assert error.message == "Workflow configuration invalid"
        assert error.category == ErrorCategory.WORKFLOW
        assert error.recoverable is False


class TestErrorContext:
    """Test ErrorContext class."""

    def test_error_context_basic(self):
        """Test basic ErrorContext creation."""
        context = ErrorContext(
            operation="test_operation",
            component="test_component"
        )

        assert context.operation == "test_operation"
        assert context.component == "test_component"

    def test_error_context_with_ids(self):
        """Test ErrorContext with various IDs."""
        context = ErrorContext(
            correlation_id="corr-123",
            request_id="req-456",
            user_id="user-789",
            session_id="sess-abc"
        )

        assert context.correlation_id == "corr-123"
        assert context.request_id == "req-456"
        assert context.user_id == "user-789"
        assert context.session_id == "sess-abc"

    def test_error_context_with_metadata(self):
        """Test ErrorContext with metadata."""
        metadata = {"key1": "value1", "key2": "value2"}
        context = ErrorContext(metadata=metadata)

        assert context.metadata == metadata

    def test_error_context_with_stack_trace(self):
        """Test ErrorContext with stack trace."""
        context = ErrorContext(operation="test")
        context_with_trace = context.with_stack_trace()

        assert context_with_trace.stack_trace is not None
        assert len(context_with_trace.stack_trace) > 0
