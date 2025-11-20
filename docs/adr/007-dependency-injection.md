# ADR-007: FastAPI Dependency Injection

## Status

**Accepted**

**Date:** 2025-11-20

## Context

Ingenious is built on FastAPI, which provides a powerful dependency injection (DI) system. The application needs to:

1. **Manage service lifecycle** - Create services once, share across requests
2. **Inject dependencies into routes** - Provide config, database, LLM services
3. **Handle configuration** - Load settings from environment/files
4. **Enable testing** - Easy to mock dependencies
5. **Avoid global state** - No singletons or module-level instances

Key services that need injection:
- **IngeniousSettings**: Application configuration
- **OpenAIService**: LLM client (expensive to create)
- **IChatHistoryRepository**: Database access
- **MultiAgentService**: Chat orchestration

Historical context:
- Earlier versions used global variables and manual initialization
- Moved to FastAPI's native DI system
- Removed custom dependency injection containers
- Simplified to pure FastAPI patterns

## Decision

Use **FastAPI's native dependency injection** with application-scoped service instances.

### Architecture

**Dependency Functions** in `fastapi_dependencies.py`:

```python
@lru_cache
def get_config() -> IngeniousSettings:
    """Get singleton config instance."""
    return IngeniousSettings()

@lru_cache  
def get_openai_service(
    config: IngeniousSettings = Depends(get_config)
) -> OpenAIService:
    """Get singleton OpenAI service."""
    return OpenAIService(config)

@lru_cache
def get_repository(
    config: IngeniousSettings = Depends(get_config)
) -> IChatHistoryRepository:
    """Get singleton repository."""
    return RepositoryFactory.create_chat_history_repository(
        db_type=config.chat_history.database_type,
        config=config
    )

def get_chat_service(
    config: IngeniousSettings = Depends(get_config),
    openai_service: OpenAIService = Depends(get_openai_service),
    repository: IChatHistoryRepository = Depends(get_repository),
) -> ChatService:
    """Get request-scoped chat service (if needed)."""
    wrapped_config = ConfigWrapper(config, openai_service)
    return MultiAgentService(wrapped_config, repository)
```

**Route Injection**:

```python
@router.post("/api/v1/chat")
async def chat(
    request: ChatRequest,
    config: IngeniousSettings = Depends(get_config),
    chat_service: ChatService = Depends(get_chat_service),
):
    """Chat endpoint with injected dependencies."""
    return await chat_service.process(request)
```

### Dependency Scopes

- **Application scope** (`@lru_cache`): Created once, shared across all requests
  - `get_config()` - Settings loaded at startup
  - `get_openai_service()` - Expensive LLM client
  - `get_repository()` - Database connection pool

- **Request scope** (no cache): New instance per request
  - `get_chat_service()` - If stateful per request
  - `get_current_user()` - Auth from request headers

### Key Principles

1. **No global state**: Everything injected, nothing at module level
2. **Pure functions**: Dependency functions have no side effects
3. **Type safety**: Full type annotations for IDE support
4. **Testability**: Can override any dependency for testing
5. **Lazy creation**: Services only created when first requested
6. **Clear lifecycle**: @lru_cache vs no cache indicates scope

## Consequences

### Positive

- **Native FastAPI**: Uses framework's built-in DI, not custom system
- **Simple**: Easy to understand, minimal abstraction
- **Type safe**: Full IDE autocomplete and type checking
- **Testable**: Override dependencies in tests with `app.dependency_overrides`
- **Explicit**: Dependencies declared in function signatures
- **Lazy loading**: Services created on first use
- **Request isolation**: Each request gets consistent dependency set
- **Debugging friendly**: Clear stack traces, no magic

### Negative

- **Manual wiring**: Must add Depends() to every route
- **Circular dependencies**: Can occur if not careful with dependency graph
- **Testing boilerplate**: Must set up dependency overrides
- **No auto-discovery**: Can't automatically find and register services
- **Duplication**: Similar Depends() chains in multiple routes
- **Scope management**: Must remember to use @lru_cache correctly

## How It Works

### Startup Sequence

1. **FastAPI app created** in `app_factory.py`
2. **Routes registered** with dependency declarations
3. **First request arrives**
4. **FastAPI resolves dependencies**:
   - Calls `get_config()` → cached for future requests
   - Calls `get_openai_service(config)` → cached
   - Calls `get_repository(config)` → cached
   - Calls `get_chat_service(...)` → created per request or cached
5. **Route handler executes** with injected services
6. **Response returned**

### Request Flow

```
HTTP Request
    ↓
FastAPI Router
    ↓
Resolve Dependencies (parallel)
    ├→ get_config() [cached]
    ├→ get_openai_service(config) [cached]  
    ├→ get_repository(config) [cached]
    └→ get_chat_service(...) [new or cached]
    ↓
Route Handler
    ↓
HTTP Response
```

### Caching with @lru_cache

```python
@lru_cache  # maxsize=128 by default
def get_config() -> IngeniousSettings:
    # Called once, result cached
    return IngeniousSettings()
```

- First call: Creates and caches instance
- Subsequent calls: Returns cached instance
- Cache key: Function arguments (none here, so always same cache entry)
- Thread-safe: lru_cache handles concurrent requests

### Testing with Dependency Overrides

```python
def test_chat_endpoint():
    # Create mocks
    mock_config = create_test_config()
    mock_service = MockChatService()
    
    # Override dependencies
    app.dependency_overrides[get_config] = lambda: mock_config
    app.dependency_overrides[get_chat_service] = lambda: mock_service
    
    # Test endpoint
    response = client.post("/api/v1/chat", json={...})
    
    # Clean up
    app.dependency_overrides.clear()
```

## Alternatives Considered

### Alternative 1: Custom Dependency Injection Container

**Description:** Use library like `dependency-injector` or custom container:

```python
from dependency_injector import containers, providers

class Container(containers.DeclarativeContainer):
    config = providers.Singleton(IngeniousSettings)
    openai_service = providers.Singleton(OpenAIService, config=config)
    repository = providers.Singleton(RepositoryFactory.create, config=config)

container = Container()
```

**Rejected because:**
- Adds external dependency
- Another DI system to learn (FastAPI already has one)
- Over-engineering for our needs
- Less integration with FastAPI features
- More complex testing setup

### Alternative 2: Global Singletons

**Description:** Module-level service instances:

```python
# services.py
CONFIG = IngeniousSettings()
OPENAI_SERVICE = OpenAIService(CONFIG)
REPOSITORY = RepositoryFactory.create(CONFIG)

# routes.py
from services import CONFIG, OPENAI_SERVICE

@router.post("/chat")
async def chat(request: ChatRequest):
    result = await OPENAI_SERVICE.process(request)
```

**Rejected because:**
- Global state is anti-pattern
- Hard to test (can't mock globals easily)
- Initialization order issues
- No request-scoped dependencies
- Tight coupling to module
- Concurrency issues if services have state

### Alternative 3: Manual Initialization in Routes

**Description:** Create services in each route:

```python
@router.post("/chat")
async def chat(request: ChatRequest):
    config = IngeniousSettings()
    openai_service = OpenAIService(config)
    repository = RepositoryFactory.create(config)
    chat_service = MultiAgentService(config, repository)
    return await chat_service.process(request)
```

**Rejected because:**
- Creates services on every request (wasteful)
- Duplicated code in every route
- Hard to test (can't inject mocks)
- No shared state (e.g., connection pools)
- Expensive service creation (OpenAI clients)

### Alternative 4: Class-Based Dependencies

**Description:** Use class-based dependency providers:

```python
class ConfigProvider:
    @staticmethod
    def get() -> IngeniousSettings:
        return IngeniousSettings()

@router.post("/chat")
async def chat(
    config: IngeniousSettings = Depends(ConfigProvider.get)
):
    pass
```

**Rejected because:**
- No benefit over function-based
- More boilerplate (class definition)
- Less idiomatic FastAPI
- Harder to cache with @lru_cache

### Alternative 5: Application State

**Description:** Store services in FastAPI app.state:

```python
@app.on_event("startup")
def startup():
    app.state.config = IngeniousSettings()
    app.state.openai_service = OpenAIService(app.state.config)

@router.post("/chat")
async def chat(request: Request):
    service = request.app.state.openai_service
```

**Rejected because:**
- No type safety (app.state is dict-like)
- Must access via request object
- No automatic dependency resolution
- Can't use Depends() chain
- Harder to test (must mock request.app.state)

## Best Practices

### DO:

```python
# ✅ Use @lru_cache for expensive, stateless services
@lru_cache
def get_openai_service(...) -> OpenAIService:
    return OpenAIService(...)

# ✅ Type annotate everything
def get_config() -> IngeniousSettings:
    return IngeniousSettings()

# ✅ Compose dependencies
def get_service(
    config: IngeniousSettings = Depends(get_config)
) -> MyService:
    return MyService(config)

# ✅ Override in tests
app.dependency_overrides[get_config] = lambda: test_config
```

### DON'T:

```python
# ❌ Don't use global variables
CONFIG = IngeniousSettings()  # Global state

# ❌ Don't cache request-scoped dependencies
@lru_cache  # Wrong! User different per request
def get_current_user(...) -> User:
    return parse_jwt(...)

# ❌ Don't create circular dependencies
def get_a(b: B = Depends(get_b)): ...
def get_b(a: A = Depends(get_a)): ...  # Circular!

# ❌ Don't mix dependency styles
CONFIG = IngeniousSettings()  # Global
def get_service(config = Depends(get_config)): ...  # DI
```

## Dependency Graph

Current dependency tree:

```
get_config()
    ↓
    ├→ get_openai_service(config)
    │      ↓
    │      └→ get_chat_service(config, openai, repo)
    │
    └→ get_repository(config)
           ↓
           └→ get_chat_service(config, openai, repo)
```

All dependencies flow from config (root of tree).

## Related Decisions

- [ADR-006: ConfigWrapper Service Injection](006-config-wrapper.md) - Wrapping multiple services
- [ADR-002: Three Database Backend Strategy](002-database-backends.md) - Repository factory pattern

## Implementation Details

### Location

- Dependency functions: `ingenious/services/fastapi_dependencies.py`
- Route usage: `ingenious/api/routes/*.py`
- Testing overrides: `tests/conftest.py`

### Adding New Dependencies

1. **Create dependency function**:
```python
@lru_cache  # If singleton
def get_my_service(
    config: IngeniousSettings = Depends(get_config)
) -> MyService:
    return MyService(config)
```

2. **Inject in routes**:
```python
@router.post("/endpoint")
async def endpoint(
    service: MyService = Depends(get_my_service)
):
    return service.do_something()
```

3. **Override in tests**:
```python
app.dependency_overrides[get_my_service] = lambda: mock_service
```

## References

- [FastAPI Dependencies Documentation](https://fastapi.tiangolo.com/tutorial/dependencies/)
- [FastAPI Advanced Dependencies](https://fastapi.tiangolo.com/advanced/advanced-dependencies/)
- [Python lru_cache](https://docs.python.org/3/library/functools.html#functools.lru_cache)
- [Dependency Injection Principles](https://martinfowler.com/articles/injection.html)
- Code: `ingenious/services/fastapi_dependencies.py`
