# Security Hardening with Bandit

Use Bandit to detect common Python security issues and refactor code safely.

## When to Use

- Before security audits
- After adding authentication or data handling code
- As part of CI/CD security checks

## Arguments

Usage: `/bandit [target] [--severity low|medium|high]`

- `target` - Directory or file to scan (default: auto-detect Python source directories)
- `--severity` - Minimum severity level to report (default: medium)

If `$ARGUMENTS` is provided, use it as the target path or options.

## Prerequisites

- bandit: `uv add --dev bandit`

## Steps

### 1. Run Bandit Scan

```bash
# Medium and high severity only (recommended)
uv run bandit -r . -ll --exclude .venv,venv,node_modules

# Full scan with all severities
uv run bandit -r . -f screen --exclude .venv,venv,node_modules
```

For specific directories:
```bash
uv run bandit -r src/ lib/
```

### 2. Parse Findings

For each issue note:
- File:Line
- Test ID (e.g., B303, B602)
- Severity / Confidence
- Short description

Create a working list sorted: High severity first, then Medium.

### 3. Classify Each Finding

Choose one:
- **TRUE_POSITIVE** - Fix now
- **NEEDS_REFACTOR** - Create safer abstraction then fix
- **FALSE_POSITIVE** - Justify and suppress locally
- **ACCEPT_RISK** - Open tracking issue with rationale and mitigation plan

### 4. Common Issues and Fixes

| Test ID | Issue | Fix |
|---------|-------|-----|
| B303/B304 | Insecure hash (MD5/SHA1) | Use `hashlib.sha256()` or `blake2b` |
| B102 | `exec()` usage | Remove or sandbox execution |
| B602-B607 | Shell injection risk | Remove `shell=True`, use args list |
| B301 | Pickle deserialization | Use JSON or safe serializer |
| B108 | Hardcoded temp directory | Use `tempfile` module |
| B105 | Hardcoded password | Move to environment variable or secret manager |
| B403 | Import pickle | Consider safer alternatives |
| B410 | `yaml.load()` | Use `yaml.safe_load()` |
| B501 | `verify=False` in requests | Enable cert validation |
| B608 | SQL injection | Use parameterized queries |

### 5. Fix Incrementally

For each finding fixed:
```bash
uv run pytest -q
uv run bandit -r <affected_path> -ll
```

Commit if clean:
```bash
git add <files>
git commit -m "security(bandit): mitigate <TestID> in <symbol>"
```

### 6. Suppress False Positives

Use the narrowest suppression with explanation:
```python
password = os.environ["DB_PASSWORD"]  # nosec B105 - loaded from environment
```

Document reasoning in code comments.

### 7. Final Quality Gate

```bash
uv run bandit -r . --exclude .venv,venv -ll
uv run pytest
uv run pre-commit run --all-files
```

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| Too many findings | Legacy codebase | Prioritize high severity, fix incrementally |
| False positives | Context not understood | Add targeted `# nosec` with explanation |
| Can't fix without refactor | Deep architectural issue | Document risk, plan refactor |

## Success Criteria

- Zero high-severity findings
- All medium-severity findings addressed or documented
- No `# nosec` without explanation
- All security fixes have tests
