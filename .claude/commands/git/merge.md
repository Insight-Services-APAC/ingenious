# Merge Pull Request

List, select, and merge pull requests with quality checks.

## When to Use

- When PRs are approved and ready to merge
- For batch merging multiple PRs
- To ensure quality before merging

## Arguments

Usage: `/pr-merge [pr-number] [--base-branch name]`

- `pr-number` - Specific PR to merge (default: list all open PRs)
- `--base-branch` - Target branch (default: main)

If `$ARGUMENTS` is provided, use it as PR number.

## Prerequisites

- GitHub CLI installed and authenticated
- Repository access with merge permissions

## Steps

### 1. List Open Pull Requests

```bash
gh pr list --state open
```

Review each PR's:
- Number, title, author
- Branch name
- Description and changes

### 2. Select PRs to Merge

Choose which PR(s) to merge. Allow multiple selections for batch processing.

### 3. Verify PR Completeness

Before merging, check PR description covers all changes:

```bash
# Get PR description
gh pr view <number> --json body

# See all changes in PR
gh pr diff <number>
```

If description is incomplete, update it to cover all modified files.

### 4. Merge Process

For each selected PR:

```bash
# Check if PR can merge cleanly
gh pr view <number> --json mergeable

# Merge the PR (preserve commits, no squash)
gh pr merge <number> --merge --admin
```

**Merge rules:**
- Use `--merge` (not `--squash` or `--rebase`)
- Use `--admin` to bypass branch protection if needed
- Do NOT delete branches after merge
- No emojis in merge commits

### 5. Quality Assurance

After merging, run quality checks:

```bash
# Switch to base branch
git checkout main
git pull origin main

# Run tests
uv run pytest              # Python
npm test                   # JavaScript

# Run linting
uv run pre-commit run --all-files
npm run lint

# Run type checks
uv run mypy . --exclude venv
npx tsc --noEmit
```

### 6. Handle Failures

If quality checks fail:
- Analyze the failure
- Fix the issue
- Commit the fix
- Re-run checks until passing

### 7. Resolve Merge Conflicts

If conflicts occur during merge:
- Analyze conflicting code
- Understand intent of both changes
- Create resolution preserving functionality
- Test the resolution

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| Merge conflict | Divergent changes | Resolve conflicts manually |
| Tests fail | Breaking change | Fix tests or revert merge |
| PR not mergeable | Needs rebase | Ask PR author to update |

## Guidelines

**Conflict Resolution:**
- Prioritize functionality preservation
- Follow existing codebase patterns
- Maintain backward compatibility

**Test Fixing:**
- Understand what test validates
- Fix underlying issue, not just test
- Update test if behavior intentionally changed

**Communication:**
- Explain each step taken
- Report conflict resolutions
- Confirm completion

## Success Criteria

- All selected PRs merged
- Quality checks pass
- No unresolved conflicts
- Commit history preserved
