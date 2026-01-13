# Lint and Test

Run tests and linting iteratively until all checks pass.

## When to Use

- Before committing changes
- After making code modifications
- To verify code quality before PR

## Arguments

Usage: `/ltest [target]`

- `target` - Directory or file to check (default: auto-detect project type)

If `$ARGUMENTS` is provided, use it as the target path.

## Steps

### 1. Detect Project Type

Determine the project type by checking for configuration files:

```bash
# Check for Python project
ls pyproject.toml uv.lock setup.py requirements.txt 2>/dev/null

# Check for JavaScript/TypeScript project
ls package.json 2>/dev/null
```

### 2. Run Tests and Linting

**For Python projects:**
```bash
uv run pytest
uv run pre-commit run --all-files
```

**For JavaScript/TypeScript projects:**
```bash
npm test
npm run lint
```

**For mixed projects (both Python and JS):**
Run both sets of commands, starting with the primary language.

### 3. Debug and Fix Iteratively

For each failure:
1. Read the error message carefully
2. Identify the root cause
3. Fix the issue in the source code
4. Re-run the failing check
5. Repeat until all checks pass

### 4. Handle Slow Tests

- Do not implement new slow tests
- Do not remove existing slow tests
- Skip slow tests during iteration if needed: `pytest -m "not slow"`

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| Test import errors | Missing dependencies | Run `uv sync` or `npm install` |
| Pre-commit hook fails | Code style issues | Let auto-fix run, then re-stage files |
| Flaky tests | Non-deterministic behavior | Identify and fix the flakiness, don't skip |

## Success Criteria

- All tests pass
- All linting checks pass
- No formatting errors
- Pre-commit hooks complete successfully
