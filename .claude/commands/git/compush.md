# Commit and Push

Generate commit message, commit changes, and push to remote.

## When to Use

- After completing a unit of work
- Before switching branches
- To save progress to remote

## Arguments

Usage: `/compush [files] [--message "msg"]`

- `files` - Specific files to commit (default: all changes)
- `--message` - Optional commit message override

If `$ARGUMENTS` is provided, use it as files to commit or message.

## Steps

### 1. Security Check

**Scan for secrets before committing:**

```bash
# Option A: detect-secrets (recommended)
git diff --cached --name-only | xargs detect-secrets scan --list-all-secrets 2>/dev/null

# Option B: gitleaks
gitleaks detect --staged --verbose 2>/dev/null

# Option C: trufflehog
git diff --cached | trufflehog filesystem --staged 2>/dev/null
```

**If secrets found:**
- Remove them immediately
- Use environment variables or secret management
- **NEVER commit files containing secrets**

For false positives, add to `.secrets.baseline` or `.gitleaksignore`.

### 2. Assess Change Scope

Review the changes:
```bash
git status
git diff --cached --stat
```

If extensive changes exist:
- Break into logical groups
- Each commit should be cohesive
- Group by: feature, bug fix, refactoring, docs, tests

### 3. Write Commit Message

Use **Conventional Commits** format: `<type>(<scope>): <description>`

**Types:**
| Type | Use For |
|------|---------|
| `feat` | New feature or functionality |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Formatting, whitespace |
| `refactor` | Code change without behavior change |
| `perf` | Performance improvement |
| `test` | Adding or modifying tests |
| `chore` | Build, dependencies, tooling |
| `security` | Security-related changes |
| `ci` | CI/CD configuration |

**Rules:**
- Scope (optional): Component affected (e.g., `auth`, `api`, `db`)
- Description: Imperative mood, under 50 characters
- Full first line under 72 characters
- No emojis
- No attribution footers

**Examples:**
```
feat(auth): add JWT token refresh endpoint
fix(db): resolve connection pool exhaustion
refactor(api): simplify request validation logic
docs: update API endpoint documentation
chore(deps): upgrade FastAPI to 0.110.0
```

### 4. Commit Changes

**Single commit (small changes):**
```bash
git add .
git commit -m "<type>(<scope>): <description>"
```

**Multiple commits (extensive changes):**
```bash
# Core functionality
git add src/feature/
git commit -m "feat(feature): add core implementation"

# Tests
git add tests/
git commit -m "test(feature): add unit tests"

# Documentation
git add docs/
git commit -m "docs(feature): add usage documentation"
```

### 5. Push to Remote

```bash
git push
```

If branch is new:
```bash
git push -u origin <branch-name>
```

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| Pre-commit hook fails | Code style issues | Fix issues, re-stage, commit again |
| Push rejected | Remote has new commits | Pull first, resolve conflicts, push |
| Secrets detected | Sensitive data in commit | Remove secrets, use env vars |

## Success Criteria

- Security scan passes (no secrets)
- Commit message follows Conventional Commits
- Changes logically grouped
- Push successful
