# ADR-003: Middleware Ordering

## Status

**Accepted**

**Date:** 2025-11-20

## Context

FastAPI processes HTTP requests through a middleware stack in LIFO (Last In, First Out) order:
- Middleware added first executes last on the request
- Middleware added last executes first on the request
- Response processing happens in reverse order

Ingenious requires three key middleware components:

1. **RequestContextMiddleware** - Injects correlation IDs and request tracking
2. **CORSMiddleware** - Handles Cross-Origin Resource Sharing for frontend apps
3. **AuthMiddleware** (optional) - Validates JWT tokens and enforces authentication

Each middleware has dependencies and requirements:
- **RequestContext** needs to set correlation ID before any other processing
- **CORS** must handle preflight requests before authentication checks
- **Auth** should only run after CORS preflight handling

The ordering matters because:
- CORS preflight requests (OPTIONS) don't include auth headers
- Correlation IDs should be available for all logging, including auth failures
- Authentication failures should still have proper CORS headers

## Decision

Middleware are added in this order in `app_factory.py`:

```python
# 1. Add RequestContext first (executes last/innermost)
app.add_middleware(RequestContextMiddleware)

# 2. Add CORS second (executes before Auth)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Add Auth last (executes first/outermost) - if enabled
if config.web_configuration.authentication.enable_global_middleware:
    setup_auth_middleware(app, config)
```

Execution flow for incoming requests:
1. **Auth** (if enabled) - Validates JWT token, rejects if invalid
2. **CORS** - Adds CORS headers, handles preflight requests
3. **RequestContext** - Adds correlation ID and request context
4. **Route Handler** - Actual endpoint logic

Response processing (reverse order):
1. **Route Handler** - Generates response
2. **RequestContext** - Logs response details with correlation ID
3. **CORS** - Ensures CORS headers are on response
4. **Auth** - (no response processing)

## Consequences

### Positive

- **Preflight requests work correctly**: OPTIONS requests bypass auth as expected
- **All requests have correlation IDs**: Available for logging in all middleware and routes
- **Failed auth has CORS headers**: Frontend can read error responses
- **Predictable behavior**: Clear ordering makes debugging easier
- **Follows best practices**: Standard pattern for FastAPI middleware
- **Flexible auth**: Can disable auth middleware for development

### Negative

- **Order is critical**: Changing order breaks functionality
- **Not immediately obvious**: LIFO nature of FastAPI middleware is counterintuitive
- **Documentation needed**: Must explicitly document why this order matters
- **Testing complexity**: Must test middleware interaction, not just isolation

## What Breaks if Order Changes

### If Auth is added before CORS:

```python
# WRONG - DO NOT DO THIS
app.add_middleware(AuthMiddleware)  # Executes outer
app.add_middleware(CORSMiddleware)  # Executes inner
```

**Breaks:**
- Preflight requests (OPTIONS) fail authentication
- Browsers reject responses due to missing CORS headers
- Frontend can't make authenticated requests

**Symptom:** Console errors like "CORS policy: No 'Access-Control-Allow-Origin' header"

### If RequestContext is added after CORS:

```python
# WRONG - DO NOT DO THIS  
app.add_middleware(CORSMiddleware)
app.add_middleware(RequestContextMiddleware)  # Executes outer
```

**Breaks:**
- CORS processing doesn't have correlation ID for logging
- Inconsistent correlation IDs in logs
- Harder to trace CORS-related issues

**Symptom:** Missing correlation IDs in CORS middleware logs

### If Auth is added before RequestContext:

```python
# WRONG - DO NOT DO THIS
app.add_middleware(RequestContextMiddleware)
app.add_middleware(AuthMiddleware)  # Executes outer
app.add_middleware(CORSMiddleware)
```

**Breaks:**
- Auth failures don't log with correlation IDs
- Harder to debug authentication issues
- Lost tracing for auth-rejected requests

**Symptom:** Auth error logs missing correlation IDs

## Alternatives Considered

### Alternative 1: Combined Middleware

**Description:** Create single middleware that does all three tasks:

```python
class CombinedMiddleware:
    async def __call__(self, request, call_next):
        # Set correlation ID
        # Handle CORS
        # Check auth
        # Call next
```

**Rejected because:**
- Violates single responsibility principle
- Harder to test each concern independently
- Less flexible - can't disable just auth
- Doesn't leverage FastAPI's built-in CORSMiddleware
- More complex maintenance

### Alternative 2: Route-Level Dependencies Instead of Middleware

**Description:** Skip auth middleware, use FastAPI dependencies on each route:

```python
@app.get("/api/v1/chat")
async def chat(user = Depends(get_current_user)):
    pass
```

**Rejected because:**
- Must add dependency to every protected route (easy to forget)
- No global auth policy
- Repetitive code across all routes
- CORS and RequestContext still need middleware
- Doesn't address the ordering question

### Alternative 3: Dependency Injection Container

**Description:** Use DI container to manage middleware order and dependencies:

```python
container.add_middleware_in_order([
    RequestContextMiddleware,
    CORSMiddleware, 
    AuthMiddleware
])
```

**Rejected because:**
- Over-engineering for simple ordering problem
- Adds complexity and abstraction
- Hides FastAPI's native middleware system
- Still need to understand ordering rules

### Alternative 4: Configuration-Driven Ordering

**Description:** Let users configure middleware order in settings:

```yaml
middleware:
  order:
    - request_context
    - cors
    - auth
```

**Rejected because:**
- Users shouldn't need to understand middleware ordering
- Wrong order breaks application silently
- No benefit over hardcoded correct order
- More configuration complexity

## Best Practices

When adding new middleware:

1. **Add after RequestContext** if it needs correlation IDs
2. **Add before Auth** if it needs to run on all requests (including unauthenticated)
3. **Test with frontend** to ensure CORS works correctly
4. **Document why** if order is critical for the new middleware
5. **Consider route dependencies** instead if only some routes need it

## Related Decisions

- [ADR-007: FastAPI Dependency Injection](007-dependency-injection.md) - Alternative to middleware for route-specific logic

## Implementation Details

### RequestContextMiddleware

Located in `ingenious/main/middleware.py`:
- Generates correlation ID for request tracing
- Makes correlation ID available via context variable
- Logs request/response with correlation ID

### CORS Configuration

Current allowed origins:
```python
origins = [
    "http://localhost",
    "http://localhost:5173",  # Vite dev server
    "http://localhost:4173",  # Vite preview
]
```

For production, configure via environment variable or settings.

### Auth Middleware Setup

Conditionally enabled via configuration:
```python
if hasattr(config.web_configuration.authentication, "enable_global_middleware"):
    setup_auth_middleware(app, config)
```

## Testing Middleware Order

Key test scenarios:
1. OPTIONS request without auth header → should succeed
2. GET request without auth header → should fail with CORS headers
3. GET request with invalid token → should fail with correlation ID logged
4. GET request with valid token → should succeed with correlation ID

## References

- [FastAPI Middleware Documentation](https://fastapi.tiangolo.com/tutorial/middleware/)
- [Starlette Middleware](https://www.starlette.io/middleware/)
- [CORS Preflight Requests](https://developer.mozilla.org/en-US/docs/Glossary/Preflight_request)
- Code: `ingenious/main/app_factory.py`
- Code: `ingenious/main/middleware.py`
