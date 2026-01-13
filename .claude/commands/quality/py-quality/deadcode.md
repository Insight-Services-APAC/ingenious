# Find and Remove Dead Code with Vulture

Use Vulture to detect unused code and safely remove it.

## When to Use

- During codebase cleanup
- Before major refactoring
- To reduce maintenance burden

## Arguments

Usage: `/vulture [target]`

- `target` - Directory or file to analyze (default: current directory)

If `$ARGUMENTS` is provided, use it as the target path.

## Prerequisites

- vulture: `uv add --dev vulture`

## Steps

### 1. Run Vulture Analysis

```bash
uv run vulture . --exclude .venv,venv,node_modules,__pycache__
```

For specific directories:
```bash
uv run vulture src/ lib/
```

### 2. Verify Each Finding

For each item detected, **thoroughly verify** whether the code is truly unused:

**Cross-check references:**
- All internal imports across the codebase
- Dynamic imports (`importlib`, `__import__`)
- Entry points in `pyproject.toml` or `setup.py`
- Config-based registries and plugin systems
- Decorator registrations
- Metaprogramming patterns

**Check for indirect usage:**
- Reflection: `getattr()`, `globals()`, `locals()`
- String-based access: `eval()`, `exec()`
- Framework magic (Django models, FastAPI routes, pytest fixtures)
- CLI command definitions
- Template references

### 3. Remove Verified Dead Code

**Only if absolutely certain the code is unused:**

1. Remove the dead code
2. Run tests immediately:
   ```bash
   uv run pytest
   ```
3. Create a separate commit:
   ```bash
   git add .
   git commit -m "chore(cleanup): remove unused <function_name>"
   ```

### 4. Handle One Item at a Time

Do not batch deletions. Process one finding at a time to maintain traceability and safety.

### 5. Create Whitelist for False Positives

If code is used but Vulture doesn't detect it, create a whitelist file:

```python
# vulture_whitelist.py
from mymodule import used_by_framework  # noqa: F401
used_by_framework  # Mark as used
```

Run with whitelist:
```bash
uv run vulture . vulture_whitelist.py --exclude .venv
```

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| Test failures after removal | Code was actually used | Revert, investigate usage pattern |
| False positive | Dynamic usage not detected | Add to whitelist |
| Import errors | Removed dependency | Check all import paths |

## Success Criteria

- All Vulture findings addressed (removed or whitelisted)
- Each removal has its own commit
- All tests pass after each removal
- No false positives remain in reports
