# Git Branch Cleanup

Find and remove stale local and remote branches safely.

## Process

### 1. Fetch Latest State

```bash
git fetch --all --prune
```

### 2. Identify Stale Branches

Analyze branches and categorize:

**Merged Branches** (safe to delete):
```bash
# Local branches merged into main
git branch --merged main | grep -v "main\|master\|\*"

# Remote branches merged into main
git branch -r --merged origin/main | grep -v "main\|master\|HEAD"
```

**Orphaned Branches** (no remote tracking):
```bash
git branch -vv | grep ': gone]'
```

**Old Branches** (no commits in 30+ days):
```bash
git for-each-ref --sort=committerdate --format='%(refname:short) %(committerdate:relative)' refs/heads/
```

### 3. Generate Report

Create a table showing:
| Branch | Status | Last Commit | Age | Recommendation |
|--------|--------|-------------|-----|----------------|
| feature/old-thing | merged | abc1234 | 45 days | Delete |
| bugfix/stale | orphaned | def5678 | 30 days | Delete |
| feature/active | tracking | ghi9012 | 2 days | Keep |

### 4. Interactive Cleanup

Use AskUserQuestion to confirm deletions in batches:
- Show branches recommended for deletion
- Let user select which to delete
- Options: "Delete all merged", "Delete all orphaned", "Select individually", "Skip"

### 5. Execute Cleanup

For approved deletions:
```bash
# Delete local branch
git branch -d branch-name  # Use -D if not fully merged but approved

# Delete remote branch (only if user explicitly approves)
git push origin --delete branch-name
```

### 6. Final Summary

Report what was cleaned:
```
## Cleanup Summary

Deleted Local Branches: X
Deleted Remote Branches: Y
Kept Branches: Z

Space recovered: approximately X MB (git gc)
```

Optionally run `git gc` to reclaim space.

## Safety Rules

- NEVER delete main, master, or the current branch
- NEVER force-delete without explicit user approval
- Always show what will be deleted before doing it
- Require confirmation for remote branch deletion
- Skip branches with unpushed commits unless user confirms

## Arguments

- `$ARGUMENTS` - Optional: "local" (only local), "remote" (only remote), "merged" (only merged branches), or number of days for age threshold (default: 30)
