# Split Large Files

Identify and split large files across the codebase to improve maintainability.

## When to Use

- When files exceed 500 lines
- When files have multiple unrelated responsibilities
- Before major refactoring efforts
- To reduce merge conflicts

## Arguments

Usage: `/large-files [target] [--threshold lines]`

- `target` - Directory to analyze (default: current project)
- `--threshold` - Line count threshold (default: 500)

If `$ARGUMENTS` is provided, use it as the target path or threshold.

## Steps

### 1. Identify Candidates

Find files meeting any of these criteria:
- Files > 500 lines
- Files with > 5 distinct classes/functions handling different concerns
- Files with multiple unrelated responsibilities
- Files violating Single Responsibility Principle

```bash
# Find large Python files
find . -name "*.py" -not -path "./.venv/*" -exec wc -l {} + | sort -rn | head -20

# Find large TypeScript/JavaScript files
find . -name "*.ts" -o -name "*.js" | grep -v node_modules | xargs wc -l | sort -rn | head -20
```

### 2. Analyze File Contents

For each large file:
- Count distinct classes/functions
- Identify separate concerns
- Map dependencies between components
- Determine natural split points

### 3. Plan Split Strategy

Separate by:
- **Domain/functionality** - Models, services, utils, validators
- **Cohesion** - Group related classes/functions together
- **Dependencies** - Minimize circular dependencies
- **Feature** - Component-based or feature-based organization

### 4. Execute Split

For each file to split:

1. Create new module structure:
   ```bash
   mkdir -p module_name/
   touch module_name/__init__.py  # Python
   touch module_name/index.ts     # TypeScript
   ```

2. Move related code to new files

3. Update imports across codebase:
   ```bash
   # Find files importing the old module
   grep -r "from old_module import" --include="*.py"
   grep -r "import.*from.*old_module" --include="*.ts"
   ```

4. Create index file for clean public API

### 5. Quality Checks

After each split:

```bash
# Verify no circular dependencies (Python)
uv run pytest --collect-only

# Verify no import errors (TypeScript)
npx tsc --noEmit

# Run tests
uv run pytest  # or npm test
```

### 6. Maintain Backward Compatibility

Where possible:
- Re-export from original location
- Add deprecation warnings for old imports
- Update documentation

### 7. Commit Incrementally

```bash
git add <new_files> <modified_files>
git commit -m "refactor(<module>): split <file> into <components>"
```

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| Circular imports | Interdependent modules | Extract shared code to separate module |
| Import errors | Missing re-exports | Update index file |
| Test failures | Broken imports | Update test imports |

## Success Criteria

- No files exceed threshold (500 lines default)
- Each file has single, clear responsibility
- No circular dependencies
- All tests pass
- Imports updated across codebase
