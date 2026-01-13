# Find and Fix mypy Errors

Use mypy to detect and fix type errors in Python code.

## When to Use

- Before committing Python code changes
- When adding type annotations to existing code
- To catch type-related bugs early

## Arguments

Usage: `/mypy [target]`

- `target` - Directory or file to check (default: current directory)

If `$ARGUMENTS` is provided, use it as the target path.

## Prerequisites

- mypy installed: `uv add --dev mypy`
- Type stubs for dependencies as needed

## Steps

### 1. Run Type Check

```bash
uv run mypy . --exclude venv --exclude .venv --exclude node_modules
```

For specific directories:
```bash
uv run mypy src/ tests/
```

### 2. Review Output

For each error, note:
- File path and line number
- Error code (e.g., `[assignment]`, `[arg-type]`, `[return-value]`)
- Error description

### 3. Common Errors and Fixes

| Error Code | Description | Fix |
|------------|-------------|-----|
| `[assignment]` | Incompatible types in assignment | Fix type or add proper annotation |
| `[arg-type]` | Argument type mismatch | Fix argument or update function signature |
| `[return-value]` | Return type mismatch | Fix return statement or annotation |
| `[name-defined]` | Name not defined | Import missing type or fix typo |
| `[attr-defined]` | Attribute not defined | Add attribute or fix access |
| `[union-attr]` | Attribute access on Optional | Add None check or use `assert` |
| `[no-untyped-def]` | Function missing type annotations | Add parameter and return types |
| `[import]` | Cannot find module | Install stubs or add to ignore list |
| `[misc]` | Various issues | Read message carefully |

### 4. Fix Iteratively

For each error:

1. **Understand the error** - Read the full message and context
2. **Fix the source** - Update code to satisfy type checker
3. **Re-run mypy** on the specific file:
   ```bash
   uv run mypy path/to/file.py
   ```
4. **Commit when clean:**
   ```bash
   git add path/to/file.py
   git commit -m "fix(types): resolve mypy errors in <module>"
   ```

### 5. Handle External Dependencies

For modules without type stubs, add to `pyproject.toml`:

```toml
[tool.mypy]
ignore_missing_imports = true

# Or ignore specific packages
[[tool.mypy.overrides]]
module = ["some_package.*", "another_package"]
ignore_missing_imports = true
```

Install type stubs when available:
```bash
uv add --dev types-requests types-PyYAML types-redis
```

### 6. Configure Strictness

Add to `pyproject.toml` for stricter checking:

```toml
[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_ignores = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
no_implicit_optional = true
```

### 7. Final Validation

```bash
uv run mypy . --exclude venv
uv run pytest
```

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| Too many errors | Strict mode on legacy code | Start with `--ignore-missing-imports`, fix incrementally |
| Stub not found | Missing type stubs | Install `types-*` package or add to ignore list |
| Conflicting types | Generic type issues | Use `TypeVar`, `Generic`, or `cast()` appropriately |
| Protocol errors | Structural typing issues | Implement required methods or use `typing.Protocol` |

## Success Criteria

- Zero mypy errors (or only intentionally suppressed ones)
- All type annotations are accurate
- No `# type: ignore` without explanation
- Tests still pass after type fixes
