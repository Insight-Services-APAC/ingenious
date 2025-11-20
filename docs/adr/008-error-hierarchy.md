# ADR-008: Error Hierarchy Design

## Status

**Accepted**

**Date:** 2025-11-20

## Context

Error handling in enterprise applications requires:

1. **Structured information** - Error code, category, severity, context
2. **Debugging support** - Stack traces, correlation IDs, component info
3. **User-friendly messages** - Different messages for users vs developers
4. **Logging integration** - Automatic structured logging
5. **Recovery guidance** - Suggest how to fix the issue
6. **Consistent API responses** - Standard error format

Common error scenarios in Ingenious:
- Configuration errors (missing API keys, invalid settings)
- Service failures (OpenAI API down, database connection lost)
- Workflow errors (agent failures, timeout, token limits)
- Resource errors (file not found, quota exceeded)
- Database errors (connection failed, query errors)

Problems with basic exceptions:
- No standard structure for error information
- Hard to distinguish error types programmatically
- No correlation IDs for distributed tracing
- User sees technical error messages
- No automatic logging integration
- Each component invents its own error handling

## Decision

Implement a **hierarchical error system** with a base `IngeniousError` class providing common functionality and specialized subclasses for different error categories.

### Architecture

**Base Error Class** (`ingenious/errors/base_error.py`):

```python
class IngeniousError(Exception):
    """Base exception for all Ingenious-specific errors."""
    
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        category: ErrorCategory = ErrorCategory.PROCESSING,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: Optional[ErrorContext] = None,
        cause: Optional[Exception] = None,
        recoverable: bool = True,
        recovery_suggestion: Optional[str] = None,
        user_message: Optional[str] = None,
    ):
        # Sets all attributes
        # Creates/enriches context with correlation ID
        # Automatically logs the error
```

**Error Categories** (`ingenious/errors/enums.py`):
```python
class ErrorCategory(Enum):
    CONFIGURATION = "configuration"    # Setup/config issues
    SERVICE = "service"                # External service failures
    DATABASE = "database"              # Database errors
    WORKFLOW = "workflow"              # Workflow execution errors
    RESOURCE = "resource"              # File/resource access
    PROCESSING = "processing"          # Data processing errors
    AUTHENTICATION = "authentication"  # Auth failures
    AUTHORIZATION = "authorization"    # Permission errors
```

**Error Severity** (`ingenious/errors/enums.py`):
```python
class ErrorSeverity(Enum):
    LOW = "low"          # Info level, can be ignored
    MEDIUM = "medium"    # Warning level, should investigate
    HIGH = "high"        # Error level, needs attention
    CRITICAL = "critical"  # Critical level, immediate action
```

**Specialized Error Classes**:

```python
# Configuration errors
class ConfigurationError(IngeniousError):
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.CONFIGURATION,
            severity=ErrorSeverity.HIGH,
            **kwargs
        )

# Workflow errors  
class WorkflowError(IngeniousError):
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            category=ErrorCategory.WORKFLOW,
            severity=ErrorSeverity.MEDIUM,
            **kwargs
        )

# And more...
```

**Error Context** (`ingenious/errors/context.py`):

```python
@dataclass
class ErrorContext:
    """Context information for errors."""
    correlation_id: str = field(default_factory=generate_correlation_id)
    component: Optional[str] = None
    operation: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
```

### Usage Examples

```python
# Raise with context
raise ConfigurationError(
    "Missing API key for OpenAI",
    recovery_suggestion="Set INGENIOUS_MODELS__0__API_KEY environment variable",
    context={"model_index": 0, "deployment": "gpt-4"}
)

# Wrap exception
try:
    response = openai_client.call()
except Exception as e:
    raise ServiceError(
        "OpenAI API call failed",
        cause=e,
        recovery_suggestion="Check API key and network connection"
    )

# Add correlation ID
error = WorkflowError("Agent timeout")
error.with_correlation_id(request.correlation_id)
raise error
```

## Consequences

### Positive

- **Structured errors**: Consistent error information across codebase
- **Automatic logging**: Errors log themselves with proper severity
- **Correlation tracking**: Request tracing via correlation IDs
- **User-friendly**: Separate messages for users and developers
- **Recovery guidance**: Errors suggest how to fix issues
- **Programmatic handling**: Error code and category for automated responses
- **Rich context**: Metadata for debugging without exposing internals
- **Causality chain**: Preserve original exception with `cause`
- **Severity classification**: Different response based on severity
- **Type safety**: Catch specific error types, not just `Exception`

### Negative

- **Boilerplate**: More code than simple `raise Exception(message)`
- **Learning curve**: Developers must understand error hierarchy
- **Over-engineering risk**: May be overkill for simple errors
- **Context management**: Must remember to add correlation IDs
- **Serialization complexity**: Converting to JSON/dict needs care
- **Testing burden**: Must test error creation and handling
- **Breaking changes**: Changing base class affects all errors

## Error Hierarchy

```
Exception (Python built-in)
    ↓
IngeniousError (base)
    ├── ConfigurationError
    │   ├── MissingConfigurationError
    │   └── InvalidConfigurationError
    │
    ├── ServiceError
    │   ├── OpenAIServiceError
    │   ├── DatabaseServiceError
    │   └── ExternalServiceError
    │
    ├── WorkflowError
    │   ├── AgentError
    │   ├── TimeoutError
    │   └── TokenLimitExceededError
    │
    ├── DatabaseError
    │   ├── ConnectionError
    │   └── QueryError
    │
    ├── ResourceError
    │   ├── FileNotFoundError
    │   └── QuotaExceededError
    │
    └── ProcessingError
        ├── ValidationError
        └── TransformationError
```

## Automatic Logging

Errors log themselves on creation:

```python
# In IngeniousError.__init__()
def _log_error(self) -> None:
    log_data = {
        "error_type": self.__class__.__name__,
        "error_code": self.error_code,
        "category": self.category.value,
        "severity": self.severity.value,
        "message": self.message,
        **self.context.to_dict(),
    }
    
    # Log with appropriate level based on severity
    if self.severity == ErrorSeverity.CRITICAL:
        logger.critical("Critical error occurred", **log_data)
    elif self.severity == ErrorSeverity.HIGH:
        logger.error("High severity error occurred", **log_data)
    # ...
```

Example log output:
```json
{
  "timestamp": "2025-11-20T10:15:30Z",
  "level": "ERROR",
  "error_type": "ConfigurationError",
  "error_code": "CONFIGURATION_ERROR",
  "category": "configuration",
  "severity": "high",
  "message": "Missing API key for OpenAI",
  "correlation_id": "abc-123-def",
  "component": "ingenious.services.openai",
  "recovery_suggestion": "Set INGENIOUS_MODELS__0__API_KEY...",
  "model_index": 0
}
```

## Alternatives Considered

### Alternative 1: Simple Exceptions

**Description:** Use Python's built-in exceptions:

```python
raise ValueError("Invalid configuration")
raise RuntimeError("Service failed")
```

**Rejected because:**
- No structured error information
- No automatic logging
- Hard to distinguish error types
- No correlation tracking
- No recovery guidance
- Poor user experience

### Alternative 2: Dictionary-Based Errors

**Description:** Return error dictionaries instead of raising:

```python
def process():
    if error:
        return {
            "error": True,
            "code": "CONFIG_ERROR",
            "message": "..."
        }
    return {"error": False, "data": ...}
```

**Rejected because:**
- Must check every function return value
- Easy to forget error handling
- Mixes success and error paths
- No stack traces
- Not Pythonic (exceptions are idiomatic)

### Alternative 3: Error Codes Only

**Description:** Standard exceptions with error codes:

```python
raise ValueError("ERROR_001: Missing API key")
```

**Rejected because:**
- Error code parsing is fragile
- No structure beyond string parsing
- No automatic logging
- No context or metadata
- Limited programmatic handling

### Alternative 4: Third-Party Error Framework

**Description:** Use library like `better-exceptions` or `pretty-errors`:

**Rejected because:**
- External dependency
- May not fit our needs exactly
- Less control over functionality
- Learning curve for library-specific features
- Our needs are specific to our domain

### Alternative 5: Flat Error List (No Hierarchy)

**Description:** Many independent error classes, no inheritance:

```python
class ConfigError(Exception): pass
class ServiceError(Exception): pass
# No common base
```

**Rejected because:**
- Can't catch "all Ingenious errors"
- No shared functionality
- Duplicated code across error classes
- Inconsistent error handling
- No polymorphism benefits

## Best Practices

### Creating New Error Types

```python
# 1. Choose appropriate parent class
class MySpecificError(WorkflowError):
    
    # 2. Set sensible defaults
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message,
            severity=ErrorSeverity.MEDIUM,  # Adjust as needed
            **kwargs
        )
```

### Raising Errors

```python
# ✅ Good - Rich context
raise WorkflowError(
    "Agent 'analyst' timed out",
    context={
        "agent_name": "analyst",
        "timeout_seconds": 30,
        "conversation_id": conv_id
    },
    recovery_suggestion="Increase timeout or simplify prompt"
)

# ❌ Bad - No context
raise WorkflowError("Timeout")
```

### Catching Errors

```python
# ✅ Catch specific types
try:
    result = process()
except ConfigurationError as e:
    # Handle config errors
    logger.error(f"Config issue: {e.recovery_suggestion}")
except WorkflowError as e:
    # Handle workflow errors
    return {"error": e.user_message}
except IngeniousError as e:
    # Handle any Ingenious error
    # ...

# ✅ Preserve context when re-raising
try:
    connect_to_db()
except Exception as e:
    raise DatabaseError(
        "Failed to connect to database",
        cause=e,  # Preserve original
        recovery_suggestion="Check connection string"
    )
```

### Testing Errors

```python
def test_configuration_error():
    with pytest.raises(ConfigurationError) as exc_info:
        validate_config(invalid_config)
    
    error = exc_info.value
    assert error.category == ErrorCategory.CONFIGURATION
    assert error.severity == ErrorSeverity.HIGH
    assert "API key" in error.message
    assert error.recovery_suggestion is not None
```

## FastAPI Integration

Errors convert to HTTP responses:

```python
# In exception_handlers.py
@app.exception_handler(IngeniousError)
async def ingenious_error_handler(request, exc: IngeniousError):
    return JSONResponse(
        status_code=get_status_code(exc),
        content={
            "error": exc.error_code,
            "message": exc.user_message,
            "details": exc.message if settings.DEBUG else None,
            "correlation_id": exc.context.correlation_id,
            "recoverable": exc.recoverable,
            "recovery_suggestion": exc.recovery_suggestion
        }
    )
```

## Related Decisions

- [ADR-003: Middleware Ordering](003-middleware-ordering.md) - Correlation ID from RequestContext

## Implementation Details

### Error Directory Structure

```
ingenious/errors/
├── __init__.py              # Export all error classes
├── base_error.py            # IngeniousError base class
├── enums.py                 # ErrorCategory, ErrorSeverity
├── context.py               # ErrorContext dataclass
├── configuration.py         # Configuration errors
├── service.py               # Service errors
├── workflow.py              # Workflow errors
├── database.py              # Database errors
├── resource.py              # Resource errors
└── collector.py             # Error collection utilities
```

### Adding Correlation IDs

```python
# In middleware
async def process_request(request):
    correlation_id = generate_correlation_id()
    request.state.correlation_id = correlation_id
    
    try:
        response = await call_next(request)
    except IngeniousError as e:
        e.with_correlation_id(correlation_id)
        raise
```

## References

- [Python Exception Hierarchy](https://docs.python.org/3/library/exceptions.html#exception-hierarchy)
- [Error Handling Best Practices](https://docs.python.org/3/tutorial/errors.html)
- [Structured Logging](https://www.structlog.org/)
- Code: `ingenious/errors/base_error.py`
- Code: `ingenious/errors/context.py`
