# Remove Emojis

Remove all emojis from the codebase while preserving code functionality.

## When to Use

- When codebase style guide prohibits emojis
- Before commits to maintain professional tone
- When cleaning up code from external contributions

## Arguments

Usage: `/rm-emojis [target]`

- `target` - Directory or file to clean (default: current project root)

If `$ARGUMENTS` is provided, use it as the target path.

## Steps

### 1. Search for Emojis

Find files containing emoji characters:

```bash
# Search for common emoji patterns in source files
grep -rn --include="*.py" --include="*.ts" --include="*.js" --include="*.vue" --include="*.md" -P '[\x{1F300}-\x{1F9FF}]|[\x{2600}-\x{26FF}]|[\x{2700}-\x{27BF}]' .
```

Or use ripgrep for faster search:
```bash
rg -n '[\p{Emoji}--\p{ASCII}]' --type py --type ts --type js --type vue --type md
```

### 2. Review and Categorize Findings

For each file with emojis, determine:
- **Remove:** Decorative emojis in comments, logs, or UI strings
- **Replace:** Emojis with semantic meaning (replace with text equivalent)
- **Keep:** Emojis in test fixtures or data files that intentionally contain them

### 3. Remove Emojis

For each file:
1. Open the file
2. Remove or replace emoji characters
3. Ensure string meaning is preserved (e.g., replace with descriptive text if needed)
4. Verify no syntax errors introduced

### 4. Exclusions

Skip the following:
- `node_modules/`, `.venv/`, `venv/`, `__pycache__/`
- Vendored or third-party code
- Test fixtures that intentionally contain emojis for testing
- Binary files

### 5. Verify Changes

```bash
# Re-run emoji search to confirm removal
rg '[\p{Emoji}--\p{ASCII}]' --type py --type ts --type js

# Run tests to ensure no breakage
uv run pytest  # or npm test
```

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| Syntax error after removal | Emoji was part of string | Ensure quotes are preserved |
| Test failure | Test expected emoji in output | Update test expectation |
| Encoding issues | File encoding mismatch | Ensure UTF-8 encoding |

## Success Criteria

- No emoji characters in source files (excluding exclusions)
- All tests pass
- No syntax or encoding errors
- Code functionality unchanged
