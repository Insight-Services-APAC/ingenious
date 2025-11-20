# Error Handling

Ingenious follows [RFC 7807 Problem Details for HTTP APIs](https://tools.ietf.org/html/rfc7807) for standardized error responses. This ensures consistent, machine-readable error messages across all API endpoints.

## Error Response Format

All errors return a JSON object following the RFC 7807 Problem Details format:

```json
{
  "type": "https://docs.ingenious.dev/errors/VALIDATION_ERROR",
  "title": "ValidationError",
  "status": 400,
  "detail": "conversation_flow is required",
  "instance": "/api/v1/chat",
  "correlation_id": "abc123-def456",
  "timestamp": "2025-01-15T10:30:00Z",
  "recoverable": true,
  "recovery_suggestion": "Provide the conversation_flow field in your request"
}
```

### Response Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | URI reference identifying the problem type. When dereferenced, provides human-readable documentation. |
| `title` | string | Yes | Short, human-readable summary of the problem type (e.g., "ValidationError"). |
| `status` | integer | Yes | HTTP status code for this occurrence (400-599). |
| `detail` | string | No | Human-readable explanation specific to this occurrence. |
| `instance` | string | No | URI reference identifying the specific occurrence (request path). |
| `correlation_id` | string | No | Request correlation ID for tracing across systems. |
| `timestamp` | string | Yes | ISO 8601 timestamp when the error occurred. |
| `recoverable` | boolean | No | Whether the error can potentially be recovered from. |
| `recovery_suggestion` | string | No | Suggestion for how to recover from this error. |

## Error Types

### Client Errors (4xx)

#### 400 Bad Request
Returned for configuration or general validation issues.

**Example Error Codes:**
- `CONFIGURATION_ERROR` - Invalid configuration provided
- `VALIDATION_ERROR` - General validation failure

```json
{
  "type": "https://docs.ingenious.dev/errors/VALIDATION_ERROR",
  "title": "ValidationError",
  "status": 400,
  "detail": "conversation_flow is required",
  "correlation_id": "req-123",
  "recoverable": true
}
```

#### 401 Unauthorized
Authentication is required or has failed.

**Example Error Codes:**
- `AUTHENTICATION_ERROR` - Invalid or missing credentials

```json
{
  "type": "https://docs.ingenious.dev/errors/AUTHENTICATION_ERROR",
  "title": "AuthenticationError",
  "status": 401,
  "detail": "Invalid authentication token",
  "correlation_id": "req-456",
  "recoverable": true,
  "recovery_suggestion": "Please provide valid authentication credentials"
}
```

#### 403 Forbidden
The request is valid but the user doesn't have permission.

**Example Error Codes:**
- `AUTHORIZATION_ERROR` - Insufficient permissions

```json
{
  "type": "https://docs.ingenious.dev/errors/AUTHORIZATION_ERROR",
  "title": "AuthorizationError",
  "status": 403,
  "detail": "Insufficient permissions to access this resource",
  "correlation_id": "req-789"
}
```

#### 404 Not Found
The requested resource doesn't exist.

**Example Error Codes:**
- `WORKFLOW_NOT_FOUND_ERROR` - Workflow does not exist
- `RESOURCE_ERROR` - Resource not found

```json
{
  "type": "https://docs.ingenious.dev/errors/WORKFLOW_NOT_FOUND_ERROR",
  "title": "WorkflowNotFoundError",
  "status": 404,
  "detail": "Workflow 'bike-insights' not found",
  "correlation_id": "req-101",
  "recovery_suggestion": "Check available workflows and use a valid workflow name"
}
```

#### 406 Not Acceptable
Content violates content filter policies.

**Example Error Codes:**
- `CONTENT_FILTER_VIOLATION` - Content filter violation

```json
{
  "type": "https://docs.ingenious.dev/errors/CONTENT_FILTER_VIOLATION",
  "title": "ContentFilterError",
  "status": 406,
  "detail": "The users prompt violates the content filter, please start a new conversation.",
  "correlation_id": "req-202",
  "recoverable": false,
  "recovery_suggestion": "Please rephrase your message to comply with content policies and start a new conversation."
}
```

#### 413 Payload Too Large
Request exceeds token limits.

**Example Error Codes:**
- `TOKEN_LIMIT_EXCEEDED` - Token limit exceeded

```json
{
  "type": "https://docs.ingenious.dev/errors/TOKEN_LIMIT_EXCEEDED",
  "title": "TokenLimitExceededError",
  "status": 413,
  "detail": "This chat has exceeded the token limit, please start a new conversation.",
  "correlation_id": "req-303",
  "recoverable": false,
  "recovery_suggestion": "Please start a new conversation or reduce the length of your messages."
}
```

#### 422 Unprocessable Entity
Request validation failed.

**Example Error Codes:**
- `REQUEST_VALIDATION_ERROR` - Request validation failed

```json
{
  "type": "https://docs.ingenious.dev/errors/REQUEST_VALIDATION_ERROR",
  "title": "RequestValidationError",
  "status": 422,
  "detail": "Invalid request format",
  "correlation_id": "req-404",
  "recovery_suggestion": "Verify your JSON structure matches the API requirements"
}
```

#### 429 Too Many Requests
Rate limit exceeded.

**Example Error Codes:**
- `RATE_LIMIT_ERROR` - Rate limit exceeded

```json
{
  "type": "https://docs.ingenious.dev/errors/RATE_LIMIT_ERROR",
  "title": "RateLimitError",
  "status": 429,
  "detail": "Rate limit exceeded",
  "correlation_id": "req-505",
  "recoverable": true
}
```

**Response Headers:**
- `Retry-After` - Number of seconds to wait before retrying
- `X-RateLimit-Reset` - Unix timestamp when the rate limit resets

### Server Errors (5xx)

#### 500 Internal Server Error
Unexpected server error occurred.

**Example Error Codes:**
- `INTERNAL_ERROR` - Unexpected internal error

```json
{
  "type": "https://docs.ingenious.dev/errors/INTERNAL_ERROR",
  "title": "InternalServerError",
  "status": 500,
  "detail": "An unexpected error occurred. Please try again.",
  "correlation_id": "req-606",
  "recoverable": true
}
```

#### 502 Bad Gateway
External service error.

**Example Error Codes:**
- `SERVICE_ERROR` - External service unavailable

```json
{
  "type": "https://docs.ingenious.dev/errors/SERVICE_ERROR",
  "title": "ServiceError",
  "status": 502,
  "detail": "External service unavailable",
  "correlation_id": "req-707",
  "recoverable": true
}
```

#### 503 Service Unavailable
Service temporarily unavailable (e.g., database issues).

**Example Error Codes:**
- `DATABASE_ERROR` - Database connection failed

```json
{
  "type": "https://docs.ingenious.dev/errors/DATABASE_ERROR",
  "title": "DatabaseError",
  "status": 503,
  "detail": "Database connection failed",
  "correlation_id": "req-808",
  "recoverable": true
}
```

#### 504 Gateway Timeout
Request timeout.

**Example Error Codes:**
- `API_ERROR` - API timeout

```json
{
  "type": "https://docs.ingenious.dev/errors/API_ERROR",
  "title": "APIError",
  "status": 504,
  "detail": "Request timeout",
  "correlation_id": "req-909",
  "recoverable": true
}
```

## Correlation IDs

Every error response includes a `correlation_id` field for request tracing. This ID is:

- Automatically generated for each request
- Included in structured logs
- Used to trace requests across services
- Helpful for debugging and support

When reporting issues, always include the correlation ID.

## Best Practices

### Error Handling in Client Code

```python
import httpx

async def make_request():
    try:
        response = await client.post("/api/v1/chat", json={
            "user_prompt": "Hello",
            "conversation_flow": "bike-insights"
        })
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        error = e.response.json()
        
        # Check if error is recoverable
        if error.get("recoverable"):
            print(f"Recoverable error: {error['detail']}")
            print(f"Suggestion: {error['recovery_suggestion']}")
            # Implement retry logic
        else:
            print(f"Non-recoverable error: {error['detail']}")
            # Handle non-recoverable error
        
        # Log correlation ID for support
        print(f"Correlation ID: {error['correlation_id']}")
```

### JavaScript/TypeScript Example

```typescript
interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  detail?: string;
  instance?: string;
  correlation_id?: string;
  timestamp: string;
  recoverable?: boolean;
  recovery_suggestion?: string;
}

async function makeRequest() {
  try {
    const response = await fetch('/api/v1/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_prompt: 'Hello',
        conversation_flow: 'bike-insights'
      })
    });
    
    if (!response.ok) {
      const error: ProblemDetail = await response.json();
      
      if (error.recoverable) {
        console.log(`Recoverable error: ${error.detail}`);
        console.log(`Suggestion: ${error.recovery_suggestion}`);
        // Implement retry logic
      } else {
        console.error(`Non-recoverable error: ${error.detail}`);
        // Handle non-recoverable error
      }
      
      console.log(`Correlation ID: ${error.correlation_id}`);
      throw new Error(error.detail);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Request failed:', error);
    throw error;
  }
}
```

## Security Considerations

- **No Internal Details**: Error messages never expose internal implementation details, stack traces, or sensitive information
- **User-Friendly Messages**: The `detail` field contains user-safe messages
- **Structured Logging**: Internal error details are logged separately for debugging
- **Correlation IDs**: Used for tracking without exposing sensitive data

## Testing Error Handling

When testing your integration with Ingenious APIs, verify:

1. Your code handles all documented error status codes
2. You parse the RFC 7807 Problem Details format correctly
3. You respect `Retry-After` headers for rate limiting
4. You implement retry logic for recoverable errors
5. You log correlation IDs for debugging

## Migration from Legacy Error Format

If you're upgrading from a previous version, note that error responses have changed from:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "conversation_flow is required",
    "correlation_id": "abc123"
  }
}
```

To RFC 7807 format:

```json
{
  "type": "https://docs.ingenious.dev/errors/VALIDATION_ERROR",
  "title": "ValidationError",
  "status": 400,
  "detail": "conversation_flow is required",
  "correlation_id": "abc123",
  "timestamp": "2025-01-15T10:30:00Z"
}
```

Update your error parsing logic accordingly.

## References

- [RFC 7807: Problem Details for HTTP APIs](https://tools.ietf.org/html/rfc7807)
- [MDN HTTP Status Codes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Status)
- [Ingenious API Documentation](../index.md)
