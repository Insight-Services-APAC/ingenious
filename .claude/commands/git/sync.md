# Pull and Merge from Main

Pull latest changes from main branch and merge into current branch.

## When to Use

- Before starting new work
- To get latest changes from team
- Before creating a PR
- When branch is behind main

## Arguments

Usage: `/gitpull [base-branch] [--strategy merge|rebase]`

- `base-branch` - Branch to pull from (default: main)
- `--strategy` - Merge strategy (default: merge)

If `$ARGUMENTS` is provided, use it as the base branch or strategy.

## Steps

### 1. Fetch Latest Changes

```bash
git fetch origin
```

### 2. Update Base Branch

```bash
git checkout main
git pull origin main
```

### 3. Return to Working Branch

```bash
git checkout -
```

### 4. Merge or Rebase

**Option A: Merge (preserves commit history)**
```bash
git merge main
```

**Option B: Rebase (cleaner linear history)**
```bash
git rebase main
```

### 5. Resolve Conflicts (if any)

If conflicts occur:

1. Identify conflicted files:
   ```bash
   git status
   ```

2. Open each conflicted file and resolve:
   - Look for markers: `<<<<<<<`, `=======`, `>>>>>>>`
   - Keep desired changes from both sides
   - Remove conflict markers

3. Stage resolved files:
   ```bash
   git add <resolved-file>
   ```

4. Continue:
   - For merge: `git commit` or `git merge --continue`
   - For rebase: `git rebase --continue`

### 6. Verify Success

```bash
git status
git log --oneline -10
```

### 7. Run Tests

```bash
# Python
uv run pytest
uv run pre-commit run --all-files

# JavaScript
npm test
npm run lint
```

### 8. Push Updated Branch

```bash
git push origin <branch-name>
```

If rebased, force push may be needed:
```bash
git push origin <branch-name> --force-with-lease
```

## Conflict Resolution Tips

**Understanding markers:**
- `<<<<<<< HEAD` - Your current branch changes
- `=======` - Separator
- `>>>>>>> main` - Main branch changes

**Resolution strategies:**
- Keep both changes (merge logically)
- Keep only main branch changes
- Keep only current branch changes
- Create new solution combining both

**Helpful commands:**
```bash
git diff                      # See differences
git log --oneline main..HEAD  # Commits unique to current branch
git log --oneline HEAD..main  # Commits unique to main
```

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| Dirty working tree | Uncommitted changes | Commit or stash changes first |
| Conflict too complex | Major divergence | Consider squashing or fresh branch |
| Rebase conflicts on each commit | Many commits | Consider merge instead |

## Success Criteria

- Latest main changes incorporated
- All conflicts resolved
- Tests pass
- Branch pushed to remote
