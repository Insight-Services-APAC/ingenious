# Contributing to Insight Ingenious

Thank you for your interest in contributing to Insight Ingenious! This document provides guidelines and instructions for contributing to the project.

## Code of Conduct

By participating in this project, you agree to abide by our code of conduct, which expects all contributors to be respectful, open-minded, and collaborative.

## Getting Started

### Prerequisites

- Python 3.13 or higher
- [uv](https://docs.astral.sh/uv/) for Python package management
- Git

### Setting Up Your Development Environment

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR-USERNAME/ingenious.git
   cd ingenious
   ```

3. Set up a development environment:
   ```bash
   uv sync --extra dev
   ```

4. Configure your project:
   ```bash
   uv init
   uv run ingen init
   ```

## Development Workflow

### Branch Strategy

- `main`: Stable production code
- Feature branches: Use format `feature/your-feature-name`
- Bug fix branches: Use format `fix/issue-description`

### Testing

Before submitting a PR, please ensure your code passes all tests:

```bash
uv run pytest
```

### Linting and Formatting

This project uses:
- [Pre-commit](https://pre-commit.com/) hooks to enforce standards

Install pre-commit hooks:
```bash
uv run pre-commit install
```

Occassionally run and run before submitting PR:
```bash
uv run pre-commit run --all-files
```

### Type Safety

This project uses:
- [mypy](https://mypy.readthedocs.io/) for static type checking

Occassionally run and run before submitting PR:
```bash
uv run mypy .
```

Refer to the mypy prompt in .github/prompts for a better understanding of expected type safety in a PR.

### Naming Conventions (PEP 8)

All Python code must follow **PEP 8 naming conventions**. This ensures consistency and maintainability across the codebase.

#### Naming Rules

1. **Classes**: Use `PascalCase` (also known as CapWords)
   - ✅ `class MultiAgentChatService:`
   - ❌ `class multi_agent_chat_service:`

2. **Functions and Methods**: Use `snake_case`
   - ✅ `def get_memory_path():`
   - ❌ `def Get_Memory_Path():` or `def GetMemoryPath():`

3. **Constants**: Use `UPPER_SNAKE_CASE`
   - ✅ `MAX_RETRIES = 3`
   - ❌ `maxRetries = 3`

4. **Variables and Parameters**: Use `snake_case`
   - ✅ `def __init__(self, category: str):`
   - ❌ `def __init__(self, Category: str):`

5. **Private Members**: Prefix with single underscore
   - ✅ `self._internal_state`
   - ❌ `self.internalState`

#### Enforcement

Naming compliance is enforced via:
- `ruff` with PEP 8 naming rules (configured in `pyproject.toml`)
- pre-commit hooks that run on every commit

Run checks manually:
```bash
uv run ruff check --select N .
```

#### Deprecation Strategy

When renaming public APIs, we follow a two-phase approach:

**Phase 1 (v0.2.8)**: Add new names with deprecation warnings on old names
```python
class MultiAgentChatService:  # New name
    def get_memory_path(self):  # New name
        return self._memory_path
    
    def Get_Memory_Path(self):  # Old name (deprecated)
        warnings.warn(
            "Get_Memory_Path is deprecated, use get_memory_path instead",
            DeprecationWarning,
            stacklevel=2
        )
        return self.get_memory_path()

# Backward compatibility alias
multi_agent_chat_service = MultiAgentChatService
```

**Phase 2 (v0.3.0)**: Remove deprecated names entirely

### Docstring Standard

All Python code must use **Google-style docstrings**. This ensures consistency and enables automated documentation generation.

#### Format Requirements

- Use triple double quotes (`"""`)
- First line: one-sentence imperative summary (e.g., "Create user account.")
- Blank line before detailed description
- Include `Args`, `Returns`, `Raises`, `Yields`, and `Attributes` sections as applicable

#### Examples

**Module docstring:**
```python
"""User authentication and authorization utilities.

This module provides functions for validating credentials, managing sessions,
and enforcing access control policies.
"""
```

**Class docstring:**
```python
class UserManager:
    """Manage user accounts and permissions.

    Attributes:
        database: Database connection for user storage.
        auth_provider: External authentication provider.
    """
```

**Function docstring:**
```python
def create_user(username: str, email: str) -> User:
    """Create a new user account.

    Args:
        username: Unique username for the account.
        email: User's email address for notifications.

    Returns:
        User: Newly created user instance.

    Raises:
        ValueError: If username is already taken.
    """
```

#### Enforcement

Docstring compliance is enforced via:
- `ruff` with pydocstyle rules (configured in `pyproject.toml`)
- pre-commit hooks that run on every commit

Run checks manually:
```bash
uv run ruff check --select D .
```

### Built-in Prompts
Please refer to the folder .github/prompts for pre-written prompts that will be helpful in developing Ingenious.

## Getting Help

If you need help, you can reach out to the maintainers

Thank you for contributing to Insight Ingenious!
