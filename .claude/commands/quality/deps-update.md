# Interactive Dependency Update

Update outdated dependencies safely with validation between updates.

## Process

### 1. Audit Current State

Run in parallel:
- `uv pip list --outdated` for Python packages
- `npm outdated` in any directory with package.json
- `pip-audit` for Python security vulnerabilities
- `npm audit` for JS security vulnerabilities

### 2. Categorize Updates

Group packages by risk level:
- **Critical**: Security vulnerabilities (update first)
- **Major**: Breaking version changes (x.0.0)
- **Minor**: Feature additions (0.x.0)
- **Patch**: Bug fixes (0.0.x)

### 3. Interactive Update Loop

For each package, starting with critical:

1. Show current version, latest version, and changelog summary if available
2. Ask user whether to update (use AskUserQuestion tool)
3. If yes:
   - Update the package (`uv add package@latest` or `npm install package@latest`)
   - Run quick validation:
     - Python: `uv run python -c "import package_name"`
     - JS: `npm run build` if available
   - If validation fails, rollback and report

### 4. Final Validation

After all updates:
- Run `uv run pytest` (if tests exist) or type check with `uv run mypy .`
- Run `npm test` or `npm run build` for JS projects
- Report summary of what was updated

## Output

Provide a summary table:
| Package | Old Version | New Version | Status |
|---------|-------------|-------------|--------|
| ... | ... | ... | Updated/Skipped/Failed |

## Notes

- Never force update if tests fail
- Commit lock file changes separately from code changes
- For major version bumps, warn about potential breaking changes
