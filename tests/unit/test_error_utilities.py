"""Test error utilities module."""

import pytest

from ingenious.errors.base_error import IngeniousError
from ingenious.errors.collector import ErrorCollector
from ingenious.errors.configuration import ConfigurationError, ValidationError
from ingenious.errors.context import ErrorContext
from ingenious.errors.database import DatabaseConnectionError
from ingenious.errors.enums import ErrorCategory, ErrorSeverity
from ingenious.errors.resource import ResourceError
from ingenious.errors.service import ExternalServiceError
from ingenious.errors.utilities import create_error, handle_exception


class TestCreateError:
    """Test create_error utility function."""

    def test_create_error_basic(self):
        """Test creating a basic error."""
        error = create_error(ConfigurationError, "Test error message")

        assert isinstance(error, ConfigurationError)
        assert error.message == "Test error message"

    def test_create_error_with_context(self):
        """Test creating an error with context."""
        context = ErrorContext(operation="test_op", component="test_component")
        error = create_error(ValidationError, "Validation failed", context=context)

        assert isinstance(error, ValidationError)
        assert error.message == "Validation failed"
        assert error.context.operation == "test_op"
        assert error.context.component == "test_component"

    def test_create_error_with_additional_fields(self):
        """Test creating an error with additional fields."""
        context = ErrorContext(operation="test")
        context.metadata = {"resource_id": "12345", "resource_type": "file"}
        error = create_error(
            ResourceError,
            "Resource not found",
            context=context
        )

        assert isinstance(error, ResourceError)
        assert error.message == "Resource not found"
        assert error.context.metadata["resource_id"] == "12345"


class TestHandleException:
    """Test handle_exception utility function."""

    def test_handle_file_not_found_exception(self):
        """Test handling FileNotFoundError."""
        exc = FileNotFoundError("File does not exist")
        error = handle_exception(exc, operation="read_file", component="storage")

        assert isinstance(error, ResourceError)
        assert str(exc) in error.message
        assert error.context.operation == "read_file"
        assert error.context.component == "storage"
        assert error.cause == exc

    def test_handle_permission_error(self):
        """Test handling PermissionError."""
        exc = PermissionError("Access denied")
        error = handle_exception(exc, operation="write_file")

        assert isinstance(error, ResourceError)
        assert "Access denied" in error.message

    def test_handle_connection_error(self):
        """Test handling ConnectionError."""
        exc = ConnectionError("Database connection failed")
        error = handle_exception(exc, component="database")

        assert isinstance(error, DatabaseConnectionError)
        assert "Database connection failed" in error.message

    def test_handle_timeout_error(self):
        """Test handling TimeoutError."""
        exc = TimeoutError("Request timed out")
        error = handle_exception(exc)

        assert isinstance(error, ExternalServiceError)
        assert "Request timed out" in error.message

    def test_handle_value_error(self):
        """Test handling ValueError."""
        exc = ValueError("Invalid value")
        error = handle_exception(exc)

        assert isinstance(error, ValidationError)
        assert "Invalid value" in error.message

    def test_handle_key_error(self):
        """Test handling KeyError."""
        exc = KeyError("missing_key")
        error = handle_exception(exc)

        assert isinstance(error, ConfigurationError)

    def test_handle_generic_exception(self):
        """Test handling generic Exception."""
        exc = Exception("Something went wrong")
        error = handle_exception(exc)

        assert isinstance(error, IngeniousError)
        assert "Something went wrong" in error.message

    def test_handle_exception_with_metadata(self):
        """Test handling exception with additional metadata."""
        exc = ValueError("Invalid input")
        error = handle_exception(
            exc,
            operation="validate_input",
            user_id="user123",
            custom_field="custom_value"
        )

        assert isinstance(error, ValidationError)
        assert error.context.operation == "validate_input"
        assert error.context.user_id == "user123"
        # custom_field should be in metadata
        assert error.context.metadata is not None
        assert error.context.metadata.get("custom_field") == "custom_value"


class TestErrorCollector:
    """Test ErrorCollector class."""

    def test_init(self):
        """Test ErrorCollector initialization."""
        collector = ErrorCollector()

        assert collector.errors == []
        assert collector.error_counts == {}

    def test_add_error(self):
        """Test adding errors to collector."""
        collector = ErrorCollector()
        error1 = ConfigurationError("Config error 1")
        error2 = ValidationError("Validation error 1")
        error3 = ConfigurationError("Config error 2")

        collector.add_error(error1)
        collector.add_error(error2)
        collector.add_error(error3)

        assert len(collector.errors) == 3
        assert collector.errors[0] == error1
        assert collector.errors[1] == error2
        assert collector.errors[2] == error3

        # Check error counts
        config_key = f"ConfigurationError:{error1.error_code}"
        validation_key = f"ValidationError:{error2.error_code}"
        assert collector.error_counts[config_key] == 2
        assert collector.error_counts[validation_key] == 1

    def test_get_errors_by_severity(self):
        """Test filtering errors by severity."""
        collector = ErrorCollector()

        # Create errors with different severities
        error1 = ConfigurationError("Error 1")
        error1.severity = ErrorSeverity.HIGH

        error2 = ValidationError("Error 2")
        error2.severity = ErrorSeverity.MEDIUM

        error3 = ResourceError("Error 3")
        error3.severity = ErrorSeverity.HIGH

        collector.add_error(error1)
        collector.add_error(error2)
        collector.add_error(error3)

        high_severity_errors = collector.get_errors_by_severity(ErrorSeverity.HIGH)
        assert len(high_severity_errors) == 2
        assert error1 in high_severity_errors
        assert error3 in high_severity_errors

        medium_severity_errors = collector.get_errors_by_severity(ErrorSeverity.MEDIUM)
        assert len(medium_severity_errors) == 1
        assert error2 in medium_severity_errors

    def test_get_errors_by_category(self):
        """Test filtering errors by category."""
        collector = ErrorCollector()

        error1 = ConfigurationError("Config error")
        error2 = ValidationError("Validation error")  # Also CONFIGURATION category
        error3 = DatabaseConnectionError("DB error")

        collector.add_error(error1)
        collector.add_error(error2)
        collector.add_error(error3)

        # Both ConfigurationError and ValidationError are CONFIGURATION category
        config_errors = collector.get_errors_by_category(ErrorCategory.CONFIGURATION)
        assert len(config_errors) == 2
        assert error1 in config_errors
        assert error2 in config_errors

        # DatabaseConnectionError is DATABASE category
        db_errors = collector.get_errors_by_category(ErrorCategory.DATABASE)
        assert len(db_errors) == 1
        assert error3 in db_errors

    def test_get_summary(self):
        """Test getting summary of collected errors."""
        collector = ErrorCollector()

        error1 = ConfigurationError("Error 1")
        error1.severity = ErrorSeverity.HIGH
        error1.recoverable = True

        error2 = ValidationError("Error 2")
        error2.severity = ErrorSeverity.MEDIUM
        error2.recoverable = False

        collector.add_error(error1)
        collector.add_error(error2)

        summary = collector.get_summary()

        assert summary["total_errors"] == 2
        assert len(summary["error_counts"]) == 2
        assert summary["recoverable_errors"] == 1
        assert summary["non_recoverable_errors"] == 1
        assert ErrorSeverity.HIGH.value in summary["by_severity"]
        assert ErrorSeverity.MEDIUM.value in summary["by_severity"]

    def test_export_to_json(self):
        """Test exporting error collection to JSON."""
        collector = ErrorCollector()

        error1 = ConfigurationError("Config error")
        error2 = ValidationError("Validation error")

        collector.add_error(error1)
        collector.add_error(error2)

        json_output = collector.export_to_json()

        assert isinstance(json_output, str)
        assert "Config error" in json_output
        assert "Validation error" in json_output
        assert "summary" in json_output
        assert "errors" in json_output
        assert "total_errors" in json_output

    def test_clear(self):
        """Test clearing collected errors."""
        collector = ErrorCollector()

        error1 = ConfigurationError("Error 1")
        error2 = ValidationError("Error 2")

        collector.add_error(error1)
        collector.add_error(error2)

        assert len(collector.errors) == 2
        assert len(collector.error_counts) == 2

        collector.clear()

        assert len(collector.errors) == 0
        assert len(collector.error_counts) == 0
