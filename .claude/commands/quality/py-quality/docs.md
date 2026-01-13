# Verify and Fix Docstrings

Use Interrogate and Pydocstyle to ensure all functions, classes, and modules have proper, consistent docstrings.

## When to Use

- When docstring coverage is low
- Before major releases
- When onboarding documentation is needed

## Arguments

Usage: `/docstrings [target]`

- `target` - Directory or file to check (default: auto-detect Python source directories)

If `$ARGUMENTS` is provided, use it as the target path.

## Prerequisites

- interrogate: `uv add --dev interrogate`
- pydocstyle: `uv add --dev pydocstyle`

## Persistence Requirement

**DO NOT STOP until ALL docstring issues are resolved.** This task requires complete coverage:
- Process every single file reported by the tools
- Fix every missing or malformed docstring
- Continue working through all modules systematically
- Re-run the analysis tools after each batch of fixes to confirm progress
- Only consider this task complete when both tools report zero issues

If context window limits approach, document remaining files in the todo list and continue in the next session.

## Steps

### 1. Detect Python Source Directories

```bash
# Find directories with Python files
find . -name "*.py" -not -path "./.venv/*" -not -path "./venv/*" -not -path "./node_modules/*" | head -20
```

### 2. Run Docstring Coverage Analysis

```bash
uv run interrogate -v <target_dir> --fail-under 100
```

This shows which modules, classes, and functions are missing docstrings.

For a summary report:
```bash
uv run interrogate <target_dir> --generate-badge /tmp/docstring-badge
```

### 3. Run Docstring Style Check

```bash
uv run pydocstyle <target_dir> --convention=google
```

Key error codes:
- D100: Missing docstring in public module
- D101: Missing docstring in public class
- D102: Missing docstring in public method
- D103: Missing docstring in public function
- D107: Missing docstring in `__init__`

### 4. Processing Order

Work through files systematically:
1. Public API functions and classes
2. Complex functions (high cyclomatic complexity)
3. Entry points and orchestration code
4. Utility functions and helpers
5. Private methods and internal functions

### 5. Docstring Standards

Use Google-style docstrings consistently:

```python
def function_name(param1: str, param2: int) -> bool:
    """Short one-line summary ending with period.

    Longer description if needed. Explain the purpose,
    not the implementation.

    Args:
        param1: Description of first parameter.
        param2: Description of second parameter.

    Returns:
        Description of return value.

    Raises:
        ValueError: When param2 is negative.
    """
```

For classes:
```python
class ClassName:
    """Short one-line summary.

    Longer description of the class purpose and usage.

    Attributes:
        attr1: Description of attribute.
        attr2: Description of attribute.
    """
```

### 6. Fix Iteratively

For each file with issues:
1. Add missing docstrings starting with public interfaces
2. Fix style violations reported by pydocstyle
3. Verify changes:
   ```bash
   uv run interrogate -v <file.py>
   uv run pydocstyle <file.py> --convention=google
   ```
4. Commit when a file passes:
   ```bash
   git add <file.py>
   git commit -m "docs(<module>): add docstrings to <file>"
   ```

### 7. Validate Coverage Improvement

After each batch of fixes:
```bash
uv run interrogate -v <target_dir> --fail-under 100
uv run pydocstyle <target_dir> --convention=google
uv run pytest
```

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| D100 in `__init__.py` | Module docstring missing | Add module-level docstring at top of file |
| D107 false positive | `__init__` is trivial | Add simple docstring or configure exception |
| Style conflicts | Different conventions | Standardize on Google style |

## Success Criteria

- `interrogate` shows 100% coverage
- `pydocstyle` reports zero violations
- All tests pass
- Docstrings follow Google convention consistently
