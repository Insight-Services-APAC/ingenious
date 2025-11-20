# ADR-005: Conversation Flow Plugin Architecture

## Status

**Accepted**

**Date:** 2025-11-20

## Context

Ingenious is a framework for building AI agent applications. Different users need different conversation patterns:

- **Classification workflows**: Analyze and categorize text
- **SQL manipulation**: Natural language to database queries  
- **Knowledge base search**: RAG (Retrieval Augmented Generation)
- **Custom business logic**: Industry-specific multi-agent flows
- **Experimental patterns**: Research and prototyping

Requirements:
1. **Easy extensibility**: Users should easily add custom flows
2. **No library modification**: Don't touch library code to add flows
3. **Override capability**: Users can replace built-in flows
4. **Namespace isolation**: Custom flows don't conflict with library flows
5. **Dynamic discovery**: Flows discovered at runtime based on configuration
6. **Security**: Production can disable built-in examples

Design constraints:
- Library provides useful example flows
- Users may want to keep some built-in flows and replace others
- Flow names come from API requests (user input)
- Must work with dependency groups (flows have different dependencies)

## Decision

Implement **conversation flows as plugins** using the dynamic import pattern with namespace fallback.

### Architecture

1. **Flow Discovery**: Flows are Python modules in specific namespaces
2. **Namespace Priority**:
   - `ingenious_extensions.conversation_flows.*` (user custom, highest priority)
   - `ingenious.ingenious_extensions_template.conversation_flows.*` (templates)
   - `ingenious.conversation_flows.*` (library built-ins, lowest priority)
3. **Flow Naming**: Hyphenated names (e.g., "bike-insights") map to module names (bike_insights)
4. **Module Structure**: Each flow module exports its agents and configuration
5. **Configuration Control**: Can disable built-in flows via `ENABLE_BUILTIN_WORKFLOWS=false`

### Directory Structure

```
# User project
my_project/
└── ingenious_extensions/
    └── conversation_flows/
        ├── __init__.py
        ├── bike_insights.py        # Custom implementation
        └── custom_workflow.py       # New workflow

# Library (for reference/templates)  
ingenious/
└── ingenious_extensions_template/
    └── conversation_flows/
        ├── classification_agent.py
        ├── knowledge_base_agent.py
        └── sql_manipulation_agent.py
```

### Usage

```python
# In API request
{
    "user_prompt": "Analyze bike sales data",
    "conversation_flow": "bike-insights"  # Hyphenated
}

# Framework resolves to module
flow_module = import_module_with_fallback(
    f"conversation_flows.{normalize_workflow_name('bike-insights')}"
    # Tries: bike_insights.py in namespaces
)
```

### Flow Module Structure

```python
# ingenious_extensions/conversation_flows/my_flow.py

from typing import Dict, List
from autogen_agentchat.agents import AssistantAgent

def get_agents(config) -> Dict[str, AssistantAgent]:
    """Define agents for this flow."""
    return {
        "analyst": AssistantAgent(
            name="analyst",
            system_message="You analyze data...",
            llm_config={"model": "gpt-4"}
        ),
        "summarizer": AssistantAgent(
            name="summarizer",
            system_message="You summarize...",
            llm_config={"model": "gpt-4"}
        )
    }

def get_flow_config() -> dict:
    """Optional flow-specific configuration."""
    return {
        "max_turns": 10,
        "timeout": 300
    }
```

## Consequences

### Positive

- **True plugin system**: Add flows without modifying library
- **Selective override**: Replace specific flows, keep others
- **Clear organization**: Flows in dedicated directory structure
- **Discoverable**: File system reflects available flows
- **Version control friendly**: Custom flows tracked separately from library
- **Testing isolation**: Can test custom flows independently
- **Security control**: Disable built-in flows in production
- **Namespace safety**: Custom flows won't break on library updates

### Negative

- **Runtime discovery**: Flow errors appear at runtime, not import time
- **No static type checking**: Can't type-check flow module structure
- **Documentation challenge**: Must explain namespace priority
- **Debugging complexity**: Stack traces cross namespace boundaries
- **IDE support limitations**: No autocomplete for flow names
- **Testing burden**: Must test namespace fallback logic
- **Module naming constraints**: Must follow Python module naming rules

## How It Works

### Flow Request Flow

1. **API receives request** with `conversation_flow: "my-workflow"`
2. **Normalize name**: "my-workflow" → "my_workflow"
3. **Try import** from namespaces in priority order:
   - `ingenious_extensions.conversation_flows.my_workflow`
   - `ingenious.ingenious_extensions_template.conversation_flows.my_workflow`
   - `ingenious.conversation_flows.my_workflow`
4. **First success** is used, others ignored
5. **Import error**: Return clear message about which namespaces were tried

### Built-in Flows

Library provides three reference implementations:

1. **classification-agent**: Sentiment analysis and categorization
2. **knowledge-base-agent**: RAG with ChromaDB or Azure AI Search
3. **sql-manipulation-agent**: Natural language to SQL

These serve as:
- Working examples for new users
- Templates to copy and modify
- Fallback implementations

Can be disabled with:
```bash
INGENIOUS_CHAT_SERVICE__ENABLE_BUILTIN_WORKFLOWS=false
```

### Custom Flow Example

```python
# Create: ingenious_extensions/conversation_flows/support_triage.py

from typing import Dict
from autogen_agentchat.agents import AssistantAgent

def get_agents(config) -> Dict[str, AssistantAgent]:
    """Triage customer support tickets."""
    
    urgency_agent = AssistantAgent(
        name="urgency_classifier",
        system_message="""Classify ticket urgency: high, medium, low.
        High: Service outage, security issue, payment failure
        Medium: Feature not working, slow performance  
        Low: Questions, feature requests
        """,
        llm_config={"model": "gpt-4"}
    )
    
    routing_agent = AssistantAgent(
        name="router",
        system_message="""Route ticket to correct team:
        - Engineering: bugs, technical issues
        - Sales: pricing, contracts
        - Success: training, best practices
        """,
        llm_config={"model": "gpt-4"}
    )
    
    return {
        "urgency_classifier": urgency_agent,
        "router": routing_agent
    }

# Use in request:
# {"user_prompt": "App crashes on login", "conversation_flow": "support-triage"}
```

## Alternatives Considered

### Alternative 1: Database-Stored Flows

**Description:** Store flow definitions in database as JSON/YAML:

```yaml
# In database
flows:
  bike-insights:
    agents:
      - name: analyst
        system_message: "..."
```

**Rejected because:**
- Limits to declarative configuration (no Python logic)
- Harder to version control
- Can't use Python libraries in flows
- Complex flows need code, not just config
- Database becomes source of truth (hard to backup/restore)

### Alternative 2: Decorator-Based Registration

**Description:** Require explicit registration with decorator:

```python
@ingenious.register_flow("bike-insights")
def get_agents(config):
    return {...}
```

**Rejected because:**
- Requires importing all modules at startup
- Defeats lazy loading
- Need central registry module
- Order-dependent behavior
- Doesn't solve override problem cleanly

### Alternative 3: Class-Based Flows with Inheritance

**Description:** Flows extend base class:

```python
class BikeInsightsFlow(ConversationFlow):
    def get_agents(self):
        return {...}
```

**Rejected because:**
- Adds abstraction without clear benefit
- Forces class-based pattern even for simple flows
- Harder for users to understand
- Still need dynamic discovery
- Inheritance complicates overrides

### Alternative 4: Configuration File Mapping

**Description:** Map flow names to Python paths in config:

```yaml
flows:
  bike-insights: my_package.flows.BikeInsights
  custom-flow: my_package.flows.CustomFlow
```

**Rejected because:**
- Duplicates information (name in config and code)
- Extra configuration step
- Must maintain separate mapping
- Doesn't leverage filesystem organization
- Still need dynamic imports

### Alternative 5: REST API Extensions

**Description:** Flows as separate microservices:

```python
# POST /api/v1/flows/bike-insights with user_prompt
# -> Forwards to http://localhost:8001/analyze
```

**Rejected because:**
- Over-engineering for most use cases
- Deployment complexity
- Network latency
- Still need local orchestration
- Authentication/authorization complexity

## Implementation Details

### Namespace Utilities

`ingenious/utils/namespace_utils.py` provides:

- `normalize_workflow_name()`: Convert "my-flow" → "my_workflow"
- `get_dir_roots()`: Find namespace directories
- Flow discovery and validation

### Multi-Agent Service

`ingenious/services/chat_services/multi_agent/service.py`:

- Imports flow modules dynamically
- Calls `get_agents()` to create agent instances
- Handles import errors gracefully
- Caches imported flows

### Creating a Custom Flow

1. **Create directory**: `mkdir -p ingenious_extensions/conversation_flows`
2. **Add `__init__.py`**: `touch ingenious_extensions/conversation_flows/__init__.py`
3. **Create flow**: `vim ingenious_extensions/conversation_flows/my_flow.py`
4. **Define agents**: Implement `get_agents(config)` function
5. **Test**: POST to `/api/v1/chat` with `"conversation_flow": "my-flow"`

### Best Practices

**DO:**
- Follow Python module naming (lowercase, underscores)
- Provide clear docstrings in flow modules
- Handle errors gracefully in agent logic
- Test flows independently
- Document required dependency groups

**DON'T:**
- Use hyphens in module names (use underscores)
- Import from other custom flows (keep independent)
- Rely on global state
- Forget to add `__init__.py`
- Commit secrets in flow code

## Security Considerations

### Disable Built-in Flows in Production

```bash
INGENIOUS_CHAT_SERVICE__ENABLE_BUILTIN_WORKFLOWS=false
```

Only serves flows from `ingenious_extensions/conversation_flows/`.

### Input Validation

Flow names are validated:
- Only alphanumeric and hyphens/underscores
- No path traversal attempts
- Import errors don't expose internals

### Code Execution

Custom flows execute arbitrary Python:
- Review custom flows before deployment
- Use secure coding practices in flows
- Consider sandboxing for untrusted flows

## Related Decisions

- [ADR-001: Dynamic Import Pattern](001-dynamic-imports.md) - Import mechanism
- [ADR-004: Optional Dependency Groups](004-dependency-groups.md) - AI dependencies
- [ADR-007: FastAPI Dependency Injection](007-dependency-injection.md) - Service wiring

## References

- [AutoGen Multi-Agent Documentation](https://microsoft.github.io/autogen/docs/topics/groupchat/group_chat/)
- [Plugin Architecture Pattern](https://www.martinfowler.com/articles/plugins.html)
- Code: `ingenious/utils/namespace_utils.py`
- Code: `ingenious/services/chat_services/multi_agent/service.py`
- Template flows: `ingenious/ingenious_extensions_template/conversation_flows/`
