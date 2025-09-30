# Pull Request Creation

## Instructions

Use GitHub CLI to create a pull request with the remote branch `to-stable`.

## Pre-PR Analysis

Before creating the PR, perform comprehensive change analysis:

1. **Review all commits**: Run `git log origin/main..HEAD --oneline` to see all commits in the PR
2. **Review all file changes**: Run `git diff origin/main..HEAD --stat` to see changed files
3. **Review detailed changes**: Run `git diff origin/main..HEAD` to see all code changes
4. **Categorize changes**: Group changes by type (features, bug fixes, refactoring, docs, tests, config)
5. **Identify impact**: Note which components/modules are affected

## PR Guidelines

**CRITICAL Requirements:**
- **NEVER include emojis** in PR titles or descriptions
- **Maintain a concise, professional tone** in all PR content
- **DO NOT add attribution footers** (e.g., no "Generated with Claude Code")
- **DO NOT use squash merge** - preserve all commits
- Use clear, descriptive PR titles in imperative mood
- **Account for ALL changes** - every modified file must be explained in PR description
- Structure PR description with clear sections:
  - Summary: Brief overview of changes
  - Changes: Detailed list of modifications by category
  - Files Modified: List all changed files with brief description
  - Impact: Note any breaking changes or migration steps

## Command Format

```sh
gh pr create --base to-stable --title "Your PR title" --body "Your PR description"
```

## Example

```sh
gh pr create --base to-stable --title "Add authentication middleware" --body "Add JWT authentication middleware for API endpoints. Includes tests and documentation."
```
