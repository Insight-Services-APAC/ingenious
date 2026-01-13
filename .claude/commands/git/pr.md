# Create Pull Request

Create a pull request using GitHub CLI with comprehensive change analysis.

## When to Use

- When feature/fix is ready for review
- To merge changes into main branch
- For code review process

## Arguments

Usage: `/pr-create [base-branch] [--title "title"]`

- `base-branch` - Target branch for PR (default: main)
- `--title` - Optional PR title override

If `$ARGUMENTS` is provided, use it as the base branch or title.

## Prerequisites

- GitHub CLI installed and authenticated: `gh auth status`
- Changes committed and pushed to remote
- Branch up to date with base branch

## Steps

### 1. Pre-PR Analysis

Understand all changes before creating PR:

```bash
# See all commits in this branch
git log origin/main..HEAD --oneline

# See all changed files
git diff origin/main..HEAD --stat

# See detailed changes
git diff origin/main..HEAD
```

### 2. Categorize Changes

Group changes by type:
- Features (new functionality)
- Bug fixes (issue resolutions)
- Refactoring (code improvements)
- Documentation (docs changes)
- Tests (test additions/changes)
- Configuration (config/build changes)

### 3. Check Branch Status

```bash
# Verify branch is pushed
git status

# Ensure up to date with base
git fetch origin
git log --oneline HEAD..origin/main  # Should be empty
```

### 4. Create PR

```bash
gh pr create --base main --title "<title>" --body "$(cat <<'EOF'
## Summary
<Brief overview of changes - 1-3 sentences>

## Changes
<Detailed list by category>

### Features
- <feature 1>

### Bug Fixes
- <fix 1>

### Refactoring
- <refactor 1>

## Files Modified
<List all changed files with brief description>

## Testing
<How changes were tested>

## Impact
<Any breaking changes or migration steps>
EOF
)"
```

### 5. PR Guidelines

**Title:**
- Use imperative mood ("Add feature" not "Added feature")
- Be specific and concise
- No emojis

**Description:**
- Account for ALL changes (every modified file)
- Clear sections (Summary, Changes, Testing, Impact)
- Note any breaking changes
- Include testing instructions

**Do NOT:**
- Use squash merge (preserve commits)
- Add attribution footers
- Include emojis

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| Branch not pushed | Local only | Run `git push -u origin <branch>` |
| PR already exists | Duplicate | Update existing PR instead |
| Base branch behind | Need to update | Run `/gitpull` first |

## Success Criteria

- PR created with comprehensive description
- All changes documented
- Base branch is correct
- PR URL returned for reference
