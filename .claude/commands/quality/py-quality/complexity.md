# Refactor Using Radon

Use Radon to identify high-complexity and low-maintainability code, then refactor safely.

## When to Use

- When code is difficult to understand or modify
- Before major feature additions to complex areas
- To improve code quality metrics

## Arguments

Usage: `/radon [target] [--threshold grade]`

- `target` - Directory or file to analyze (default: current directory)
- `--threshold` - Minimum complexity grade to report (default: C)

If `$ARGUMENTS` is provided, use it as the target path.

## Prerequisites

- radon: `uv add --dev radon`

## Steps

### 1. Run Radon Reports

```bash
# Cyclomatic complexity (A=best, F=worst)
uv run radon cc -s -a . --exclude "venv/*,.venv/*"

# Maintainability Index (100=best, 0=worst)
uv run radon mi -s . --exclude "venv/*,.venv/*"

# Halstead metrics (optional, for detailed analysis)
uv run radon hal . --exclude "venv/*,.venv/*"
```

Record functions/classes with:
- Complexity grade >= C (or numeric > 10)
- Maintainability Index < 65

### 2. Prioritize Hotspots

Rank by:
1. Worst grade (F, E, D first)
2. Frequency of change (`git log -p --follow <file>`)
3. Business criticality

### 3. Establish Safety Net

For each target file/function:
1. Add or improve focused tests (behavioral, edge cases, error paths)
2. Run tests before refactoring:
   ```bash
   uv run pytest tests/test_<module>.py -v
   ```

### 4. Refactor Tactics

Apply one tactic at a time:

- **Extract Function/Method** - Break out cohesive blocks
- **Decompose Conditionals** - Use strategy maps, dict dispatch, guard clauses
- **Remove Duplication** - DRY or inline trivial indirections
- **Simplify Boolean Logic** - Early returns, De Morgan's laws
- **Replace Deep Nesting** - Fail-fast exits, extract methods
- **Clarify Names** - Rename unclear variables/functions
- **Isolate Side Effects** - Separate pure logic from I/O
- **Reduce Parameters** - Introduce dataclass or typed object
- **Split Large Classes** - Single Responsibility Principle

After each micro-change:
```bash
uv run pytest tests/test_<module>.py
uv run radon cc -s <target_file>
uv run radon mi -s <target_file>
```

Commit if green:
```bash
git add <target_file> tests/
git commit -m "refactor(radon): reduce complexity in <symbol> (C->B)"
```

### 5. Validate No Regression

When a file is improved:
```bash
uv run radon cc -s -a .
uv run radon mi -s .
uv run pytest
uv run pre-commit run --all-files
```

### 6. Know When to Stop

Stop refactoring when:
- Complexity <= B grade
- Maintainability Index >= 70
- Further changes risk unnecessary churn
- Code is clear and testable

### 7. Handle Hard Cases

If complexity resists decomposition:
- Introduce a decision table or data-driven structure
- Split algorithm into phases (parse -> transform -> emit)
- Accept temporary adapter layer while migrating callers

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| Tests fail after refactor | Behavior changed | Revert, write more tests first |
| Complexity stays high | Algorithm inherently complex | Document, add tests, accept |
| Metrics conflict | CC low but MI low | Focus on readability over metrics |

## Success Criteria

- No functions with complexity grade >= C
- Maintainability Index >= 65 for all modules
- All tests pass
- Code is more readable and maintainable
