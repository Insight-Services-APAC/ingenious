# Security Hardening with ESLint and npm audit

Use ESLint security plugins and npm audit to detect JavaScript/TypeScript security issues.

## When to Use

- Before security audits
- After adding authentication or data handling code
- As part of CI/CD security checks

## Arguments

Usage: `/audit [target]`

- `target` - Directory to scan (default: auto-detect from package.json location)

If `$ARGUMENTS` is provided, use it as the target path.

## Prerequisites

- Node.js project with package.json
- ESLint configured (optional but recommended)

## Steps

### 1. Find JavaScript/TypeScript Source Directories

```bash
# Find directories with JS/TS files
find . -name "*.ts" -o -name "*.js" -o -name "*.vue" | grep -v node_modules | head -20
```

### 2. Run Dependency Security Scan

```bash
# Check for vulnerable dependencies
npm audit

# Only moderate and above
npm audit --audit-level=moderate

# JSON output for parsing
npm audit --json
```

### 3. Run ESLint Security Rules

```bash
# Run ESLint with security focus
npx eslint . --ext .js,.ts,.vue --rule 'no-eval: error'
```

### 4. Install Security Plugins (if missing)

```bash
npm install -D eslint-plugin-security @typescript-eslint/eslint-plugin
```

Add to ESLint config (`.eslintrc.js` or `eslint.config.js`):
```javascript
{
  plugins: ['security'],
  extends: ['plugin:security/recommended-legacy']
}
```

### 5. Common Security Issues

| Rule | Issue | Risk |
|------|-------|------|
| detect-object-injection | Bracket notation with user input | Object prototype pollution |
| detect-non-literal-fs-filename | Dynamic file paths | Path traversal |
| detect-non-literal-regexp | User input in regex | ReDoS |
| detect-eval-with-expression | eval() with variables | Code injection |
| detect-no-csrf-before-method-override | CSRF vulnerability | Cross-site request forgery |
| detect-possible-timing-attacks | String comparison timing | Information leak |

### 6. Fix Patterns

| Issue | Fix |
|-------|-----|
| `eval()` / `new Function()` | Use safe alternatives, `JSON.parse()` for data |
| `innerHTML` / `dangerouslySetInnerHTML` | Use `textContent` or sanitize with DOMPurify |
| Dynamic `require()` | Use static imports |
| Unvalidated redirects | Whitelist allowed URLs |
| SQL/NoSQL injection | Use parameterized queries |
| Prototype pollution | Freeze objects, use `Object.create(null)` |

### 7. Fix Incrementally

For each finding:
```bash
npm test
npx eslint <affected_files>
```

Commit if clean:
```bash
git add <files>
git commit -m "security(eslint): mitigate <issue> in <file>"
```

### 8. Suppress False Positives

Use eslint-disable comments sparingly with explanation:
```javascript
// eslint-disable-next-line security/detect-object-injection -- key is validated enum
const value = obj[validatedKey];
```

### 9. Final Quality Gate

```bash
npm audit --audit-level=high
npx eslint . --ext .js,.ts,.vue
npm test
```

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| npm audit shows vulnerabilities | Outdated dependencies | Run `npm audit fix` or update manually |
| ESLint plugin conflicts | Version mismatch | Check peer dependencies |
| Too many findings | Legacy codebase | Prioritize high severity |

## Success Criteria

- Zero high-severity npm audit findings
- Zero ESLint security violations (or documented exceptions)
- All security fixes have tests
