# ADR-006: ConfigWrapper Service Injection

## Status

**Accepted**

**Date:** 2025-11-20

## Context

FastAPI dependency injection system allows injecting services into route handlers:

```python
@app.post("/api/v1/chat")
async def chat(
    openai_service: OpenAIService = Depends(get_openai_service),
    config: IngeniousSettings = Depends(get_config)
):
    # Use openai_service and config
    pass
```

However, some parts of the codebase (particularly chat services) need:
1. **Configuration object** - Settings for the application
2. **OpenAI service instance** - For LLM interactions
3. **Single parameter** - To simplify function signatures

The challenge: FastAPI dependencies don't naturally pass multiple related objects as one parameter.

**Option A**: Pass both separately
```python
def create_service(config: IngeniousSettings, openai_service: OpenAIService):
    pass
```

**Option B**: Create wrapper that combines both
```python
def create_service(config_with_service: ConfigWrapper):
    # config_with_service.models works  
    # config_with_service.openai_service_instance works
    pass
```

The chat service initialization pattern looks like:
```python
# In fastapi_dependencies.py
chat_service = multi_agent_service.MultiAgentService(
    wrapped_config,  # Contains both config and openai_service
    repository
)
```

Historical context:
- Earlier versions used separate parameters
- Chat services need access to both config and OpenAI service
- OpenAI service is expensive to create (should be singleton)

## Decision

Use **ConfigWrapper proxy pattern** that combines config and OpenAI service into a single injectable object.

### Implementation

```python
class ConfigWrapper:
    """Proxy that adds openai_service to config object."""
    
    def __init__(self, config: IngeniousSettings, openai_service: OpenAIService):
        self._config = config
        self.openai_service_instance = openai_service
    
    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to wrapped config."""
        return getattr(self._config, name)

# Create and use
wrapped_config = ConfigWrapper(config, openai_service)
chat_service = MultiAgentService(wrapped_config, repository)
```

The wrapper:
1. **Stores** both config and openai_service
2. **Delegates** config attribute access via `__getattr__`
3. **Exposes** openai_service as direct attribute
4. **Maintains** single parameter for service constructors

### Attribute Access Pattern

```python
# These work identically:
config.models[0].api_key
wrapped_config.models[0].api_key  # Delegated via __getattr__

# This is new:
wrapped_config.openai_service_instance  # Direct access
```

## Consequences

### Positive

- **Simplified signatures**: Services take one parameter instead of two
- **Service bundling**: Config and its dependent services travel together
- **Transparent access**: Config attributes accessed normally via delegation
- **Dependency management**: OpenAI service created once, shared via wrapper
- **Backwards compatible**: Existing config access patterns still work
- **Explicit intent**: Clear that openai_service belongs with config

### Negative

- **Magic behavior**: `__getattr__` delegation may confuse developers
- **Hidden complexity**: Not obvious wrapper exists without reading code
- **Type checking issues**: Type checkers see ConfigWrapper, not underlying config type
- **Debugging difficulty**: Stack traces show wrapper, not original config
- **Name collision risk**: If config adds `openai_service_instance`, wrapper breaks
- **Testing complexity**: Must create wrapper with both dependencies for tests
- **Documentation burden**: Must explain why wrapper exists

## What Problems Does This Solve?

### Problem 1: Dependency Proliferation

**Without wrapper:**
```python
class MultiAgentService:
    def __init__(
        self,
        config: IngeniousSettings,
        openai_service: OpenAIService,
        repository: IChatHistoryRepository,
        maybe_more_services: SomeService,
        # Constructor gets longer...
    ):
        pass
```

**With wrapper:**
```python
class MultiAgentService:
    def __init__(
        self,
        config: ConfigWrapper,  # Bundles config + openai_service
        repository: IChatHistoryRepository,
    ):
        pass
```

### Problem 2: OpenAI Service Lifecycle

OpenAI service should be singleton (expensive to create):
- With wrapper: Created once in dependency injection, shared via wrapper
- Without wrapper: Must pass separately everywhere or recreate

### Problem 3: Service-Config Coupling

OpenAI service configuration comes from config:
- With wrapper: Natural association, they travel together
- Without wrapper: Must pass both and maintain relationship manually

## Alternatives Considered

### Alternative 1: Separate Parameters

**Description:** Pass config and openai_service separately:

```python
class MultiAgentService:
    def __init__(
        self,
        config: IngeniousSettings,
        openai_service: OpenAIService,
        repository: IChatHistoryRepository,
    ):
        self.config = config
        self.openai_service = openai_service
```

**Rejected because:**
- More parameters in every service constructor
- Both always needed together (tight coupling)
- Repetitive in every service that needs LLM
- Harder to add new services later (must update all constructors)

### Alternative 2: Dependency Injection in Service

**Description:** Service gets config, creates OpenAI service internally:

```python
class MultiAgentService:
    def __init__(self, config: IngeniousSettings, ...):
        self.config = config
        self.openai_service = OpenAIService(config)  # Create here
```

**Rejected because:**
- Creates multiple OpenAI service instances (wasteful)
- Harder to test (can't inject mock service)
- Violates dependency inversion principle
- Service owns dependency lifecycle (tight coupling)

### Alternative 3: Context Manager

**Description:** Use context object for request-scoped state:

```python
class RequestContext:
    config: IngeniousSettings
    openai_service: OpenAIService
    repository: IChatHistoryRepository

# Pass context everywhere
def create_service(ctx: RequestContext):
    pass
```

**Rejected because:**
- Over-engineering for simple use case
- Context implies request scope, but services are application scope
- All services would need context (wide refactoring)
- Loses type safety (context is bag of stuff)

### Alternative 4: Config Inheritance

**Description:** Create subclass that includes service:

```python
class IngeniousSettingsWithServices(IngeniousSettings):
    openai_service: OpenAIService
    
    def __init__(self, ...):
        super().__init__(...)
        self.openai_service = OpenAIService(self)
```

**Rejected because:**
- Modifies config class (should be pure data)
- Config becomes factory (violates SRP)
- Harder to test
- Breaks separation of concerns (config ≠ services)

### Alternative 5: Getter Functions

**Description:** Config provides methods to get services:

```python
class IngeniousSettings:
    def get_openai_service(self) -> OpenAIService:
        return OpenAIService(self)
```

**Rejected because:**
- Creates new service on each call (unless cached)
- If cached, config manages service lifecycle (wrong responsibility)
- Config class grows with service factory methods
- Testing requires mocking config methods

### Alternative 6: Service Locator

**Description:** Global service registry:

```python
ServiceRegistry.register("openai", openai_service)
ServiceRegistry.register("config", config)

# In service
openai_service = ServiceRegistry.get("openai")
```

**Rejected because:**
- Global state is anti-pattern
- Hard to test (must reset registry)
- Hidden dependencies (not in constructor)
- Runtime errors for missing services
- Goes against FastAPI's DI philosophy

## When to Use This Pattern

**Use ConfigWrapper when:**
- Service A and Service B are always used together
- Service B is configured by Service A
- Want to simplify constructor signatures
- Service B is expensive to create (singleton pattern)

**Don't use when:**
- Services are independent
- Services used in different contexts separately
- Clear separation improves architecture
- Type safety is critical

## Implementation Details

### Location

`ingenious/services/fastapi_dependencies.py` lines 74-82:

```python
class ConfigWrapper:
    def __init__(self, config: IngeniousSettings, openai_service: OpenAIService):
        self._config = config
        self.openai_service_instance = openai_service

    def __getattr__(self, name: str) -> Any:
        return getattr(self._config, name)

wrapped_config = ConfigWrapper(config, openai_service)
```

### Dependency Injection Setup

```python
async def get_wrapped_config(
    config: IngeniousSettings = Depends(get_config),
    openai_service: OpenAIService = Depends(get_openai_service),
) -> ConfigWrapper:
    return ConfigWrapper(config, openai_service)
```

### Testing

```python
def test_chat_service():
    config = create_test_config()
    openai_service = MockOpenAIService()
    wrapped = ConfigWrapper(config, openai_service)
    
    service = MultiAgentService(wrapped, mock_repository)
    # Test service...
```

## Potential Improvements

### Type Safety Enhancement

```python
from typing import Protocol

class ConfigWithService(Protocol):
    """Protocol for config with OpenAI service."""
    openai_service_instance: OpenAIService
    models: List[ModelConfig]
    # ... other config attributes
    
class ConfigWrapper(ConfigWithService):
    # Now type checkers understand the interface
```

### Generic Wrapper

```python
class ServiceWrapper(Generic[TConfig]):
    """Generic wrapper for config + services."""
    
    def __init__(self, config: TConfig, **services):
        self._config = config
        self._services = services
    
    def __getattr__(self, name: str) -> Any:
        if name in self._services:
            return self._services[name]
        return getattr(self._config, name)
```

## Related Decisions

- [ADR-007: FastAPI Dependency Injection](007-dependency-injection.md) - DI patterns
- Service lifecycle management patterns

## References

- [Proxy Pattern](https://refactoring.guru/design-patterns/proxy)
- [Dependency Injection](https://martinfowler.com/articles/injection.html)
- [FastAPI Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/)
- Code: `ingenious/services/fastapi_dependencies.py`
