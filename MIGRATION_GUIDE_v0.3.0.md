# Migration Guide: v0.2.8 to v0.3.0

This guide helps you migrate your code from the deprecated naming conventions to PEP 8 compliant names.

## Overview

Version 0.2.8 introduced PEP 8 compliant naming conventions with backward compatibility through deprecation warnings. Version 0.3.0 will remove all deprecated names. This guide helps you prepare for that transition.

## Changes

### 1. FileStorage Parameter Rename

**Old (deprecated):**
```python
from ingenious.files.files_repository import FileStorage

fs = FileStorage(config, Category="data")
fs = FileStorage(config, Category="revisions")
```

**New (PEP 8 compliant):**
```python
from ingenious.files.files_repository import FileStorage

fs = FileStorage(config, category="data")
fs = FileStorage(config, category="revisions")
```

### 2. MultiAgentChatService Class Rename

**Old (deprecated):**
```python
from ingenious.services.chat_services.multi_agent.service import multi_agent_chat_service

service = multi_agent_chat_service(config, chat_history_repo, "my-flow")
```

**New (PEP 8 compliant):**
```python
from ingenious.services.chat_services.multi_agent.service import MultiAgentChatService

service = MultiAgentChatService(config, chat_history_repo, "my-flow")
```

**Note:** The old name `multi_agent_chat_service` is aliased to `MultiAgentChatService` in v0.2.8 for backward compatibility.

### 3. IConversationPattern Method Renames

If you have classes extending `IConversationPattern`, update method calls:

| Old Method (deprecated)  | New Method (PEP 8)    |
|--------------------------|----------------------|
| `GetConfig()`            | `get_config()`       |
| `Get_Models()`           | `get_models()`       |
| `Get_Memory_Path()`      | `get_memory_path()`  |
| `Get_Memory_File()`      | `get_memory_file()`  |
| `Maintain_Memory(...)`   | `maintain_memory(...)` |

**Example - Old (deprecated):**
```python
class MyPattern(IConversationPattern):
    def __init__(self):
        super().__init__()
        config = self.GetConfig()
        models = self.Get_Models()
        path = self.Get_Memory_Path()
        self.Maintain_Memory("new content")
```

**Example - New (PEP 8 compliant):**
```python
class MyPattern(IConversationPattern):
    def __init__(self):
        super().__init__()
        config = self.get_config()
        models = self.get_models()
        path = self.get_memory_path()
        self.maintain_memory("new content")
```

### 4. IConversationFlow Method Renames

If you have classes extending `IConversationFlow`, update method calls:

| Old Method (deprecated)  | New Method (PEP 8)    |
|--------------------------|----------------------|
| `GetConfig()`            | `get_config()`       |
| `Get_Template(...)`      | `get_template(...)` (async) |
| `Get_Models()`           | `get_models()`       |
| `Get_Memory_Path()`      | `get_memory_path()`  |
| `Get_Memory_File()`      | `get_memory_file()`  |
| `Maintain_Memory(...)`   | `maintain_memory(...)` |

**Example - Old (deprecated):**
```python
class MyFlow(IConversationFlow):
    def __init__(self, parent_multi_agent_chat_service):
        super().__init__(parent_multi_agent_chat_service)
        
    async def get_conversation_response(self, chat_request):
        config = self.GetConfig()
        template = await self.Get_Template(revision_id="v1")
        models = self.Get_Models()
        self.Maintain_Memory("context")
```

**Example - New (PEP 8 compliant):**
```python
class MyFlow(IConversationFlow):
    def __init__(self, parent_multi_agent_chat_service):
        super().__init__(parent_multi_agent_chat_service)
        
    async def get_conversation_response(self, chat_request):
        config = self.get_config()
        template = await self.get_template(revision_id="v1")
        models = self.get_models()
        self.maintain_memory("context")
```

## Automated Migration

You can use the following regex patterns to help automate migration:

### Find and Replace Patterns

1. **FileStorage Category parameter:**
   - Find: `Category=`
   - Replace: `category=`

2. **Class name:**
   - Find: `multi_agent_chat_service`
   - Replace: `MultiAgentChatService`

3. **Method calls (use regex):**
   - Find: `\.GetConfig\(`
   - Replace: `.get_config(`
   
   - Find: `\.Get_Models\(`
   - Replace: `.get_models(`
   
   - Find: `\.Get_Memory_Path\(`
   - Replace: `.get_memory_path(`
   
   - Find: `\.Get_Memory_File\(`
   - Replace: `.get_memory_file(`
   
   - Find: `\.Maintain_Memory\(`
   - Replace: `.maintain_memory(`
   
   - Find: `\.Get_Template\(`
   - Replace: `.get_template(`

## Testing Your Migration

After updating your code, run the following checks:

1. **Check for deprecation warnings:**
   ```bash
   uv run pytest -W default::DeprecationWarning
   ```

2. **Run naming convention checks:**
   ```bash
   uv run ruff check --select N .
   ```

3. **Run your test suite:**
   ```bash
   uv run pytest
   ```

## Timeline

- **v0.2.8 (Current)**: Both old and new names work. Old names show deprecation warnings.
- **v0.3.0 (Next Major)**: Old names removed. Only new PEP 8 compliant names work.

## Need Help?

If you encounter issues during migration:

1. Check the deprecation warnings - they include the recommended replacement
2. Review the examples in this guide
3. Consult the [CONTRIBUTING.md](CONTRIBUTING.md) for naming standards
4. Open an issue on GitHub if you find bugs or need clarification

## Summary of PEP 8 Naming Rules

- **Classes**: `PascalCase` (e.g., `MultiAgentChatService`)
- **Functions/Methods**: `snake_case` (e.g., `get_config()`)
- **Parameters**: `snake_case` (e.g., `category="data"`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `MAX_RETRIES = 3`)
- **Private members**: Leading underscore (e.g., `_internal_method()`)
