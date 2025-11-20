# ADR-001: Dynamic Import Pattern

## Status

**Accepted**

**Date:** 2025-11-20

## Context

Ingenious needs to support a plugin architecture where conversation flows, database backends, and other components can be:

1. **Provided by users** in their own projects without modifying the core library
2. **Discovered automatically** without explicit registration code
3. **Overridden selectively** - users can replace built-in implementations with custom ones
4. **Loaded conditionally** - only import what's needed based on configuration

Traditional import approaches have limitations:

- **Static imports** (`from module import Class`) require all code to be present at import time
- **Explicit registration** requires users to manually register their plugins
- **Entry points** (setuptools) add complexity and require package installation

The codebase is organized with multiple namespaces:
- `ingenious_extensions` - User custom implementations (highest priority)
- `ingenious.ingenious_extensions_template` - Example/template implementations
- `ingenious` - Core library implementations (fallback)

## Decision

Use **string-based dynamic imports** with **namespace fallback** via the `SafeImporter` class in `ingenious/utils/imports.py`.

Key features:

1. **String-based module paths**: Components are specified as strings (e.g., `"conversation_flows.bike_insights"`)
2. **Namespace fallback chain**: Try importing from namespaces in priority order
3. **Import caching**: Cache successful imports and failed attempts for performance
4. **Comprehensive error handling**: Detailed error messages with attempted paths
5. **Validation**: Verify imported modules/classes meet expected requirements

```python
# Example usage
importer = SafeImporter()
FlowClass = importer.import_class_with_fallback(
    "conversation_flows.bike_insights",
    "BikeInsightsFlow"
)
```

The fallback order is:
1. `ingenious_extensions.conversation_flows.bike_insights` (user custom)
2. `ingenious.ingenious_extensions_template.conversation_flows.bike_insights` (template)
3. `ingenious.conversation_flows.bike_insights` (core library)

## Consequences

### Positive

- **True plugin architecture**: Users can add custom flows without touching library code
- **Namespace isolation**: User code doesn't conflict with library code
- **Selective overrides**: Users can override specific components while using others
- **Lazy loading**: Only load what's configured, reducing memory footprint
- **Graceful degradation**: Missing optional components don't crash the application
- **Development flexibility**: Template examples can be used during development
- **Clear priority**: Explicit namespace ordering makes behavior predictable

### Negative

- **IDE autocomplete limitations**: IDEs can't discover string-based imports
- **Type checking gaps**: Static type checkers (mypy, pyright) can't validate string imports
- **Runtime discovery**: Import errors only appear at runtime, not during static analysis
- **Debugging complexity**: Stack traces may be less clear with dynamic imports
- **Performance overhead**: Import resolution and caching add minimal overhead
- **Learning curve**: New contributors must understand the namespace system

## Alternatives Considered

### Alternative 1: Explicit Registration Pattern

**Description:** Require users to call a registration function to add their plugins:

```python
from ingenious import register_flow
register_flow("bike-insights", BikeInsightsFlow)
```

**Rejected because:**
- Requires boilerplate code in every user project
- Must be called before app starts, complicating initialization order
- Doesn't support lazy loading
- Less intuitive for users

### Alternative 2: Python Entry Points (setuptools)

**Description:** Use setuptools entry points for plugin discovery:

```toml
[project.entry-points."ingenious.flows"]
bike_insights = "my_package.flows:BikeInsightsFlow"
```

**Rejected because:**
- Requires package installation - can't just add files to a directory
- More complex setup for simple use cases
- Harder to override specific components
- Less transparent - "magic" discovery behavior

### Alternative 3: Configuration-Based Import Mapping

**Description:** Use configuration file to map flow names to Python paths:

```yaml
flows:
  bike-insights: my_package.flows.BikeInsightsFlow
```

**Rejected because:**
- Adds configuration overhead
- Still requires dynamic imports (doesn't solve the core challenge)
- Duplicates information (name in config and in module path)
- Less discoverable - must look at config to understand structure

### Alternative 4: Decorator-Based Auto-Registration

**Description:** Use decorators to automatically register flows:

```python
@ingenious.register_flow("bike-insights")
class BikeInsightsFlow:
    pass
```

**Rejected because:**
- Requires importing all modules at startup to trigger decorators
- Defeats lazy loading benefits
- Creates implicit dependencies based on import order
- Still needs namespace management for overrides

## Related Decisions

- [ADR-005: Conversation Flow Plugin Architecture](005-conversation-flow-plugins.md)
- [ADR-004: Optional Dependency Groups](004-dependency-groups.md)

## Implementation Details

The `SafeImporter` class provides:

- `import_module_with_fallback()` - Import module from namespace chain
- `import_class_with_fallback()` - Import class from namespace chain
- `import_module()` - Direct import with error handling
- `import_class()` - Direct class import with validation
- `validate_dependencies()` - Check if required packages are available
- `clear_cache()` - Clear import caches (useful for testing)

Used throughout the codebase for:
- Conversation flow discovery (`services/chat_services/multi_agent/service.py`)
- Database backend selection (`db/repository_factory.py`)
- Custom agent loading
- Extension point discovery

## References

- [Python importlib documentation](https://docs.python.org/3/library/importlib.html)
- [Plugin Architecture Patterns](https://www.martinfowler.com/articles/plugins.html)
- Code: `ingenious/utils/imports.py`
- Code: `ingenious/utils/namespace_utils.py`
