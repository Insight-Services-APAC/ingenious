# Code Quality Janitor

Run code quality checks in parallel using subagents and git worktrees, then merge all fixes.

## When to Use

- During scheduled code quality improvements
- Before major releases
- To clean up accumulated technical debt

## Arguments

Usage: `/janitor [target-branch] [--tools list]`

- `target-branch` - Branch to merge fixes into (default: current branch)
- `--tools` - Comma-separated list of tools to run (default: all)

If `$ARGUMENTS` is provided, use it as the target branch or tool list.

## Prerequisites

- Git repository with clean working tree
- All quality tools installed (or will be installed per tool)

## Tools Available

**Python:**
- `/bandit` - Security linter
- `/docstrings` - Docstring checker
- `/mypy` - Type checker
- `/radon` - Complexity metrics
- `/vulture` - Dead code finder

**JavaScript/TypeScript:**
- `/audit` - Dependency vulnerability scan
- `/complexity` - Code complexity analysis
- `/jsdoc` - Documentation checker
- `/knip` - Unused exports/dependencies
- `/tsc` - TypeScript compiler checks

## Steps

### 1. Create Git Worktrees

Create a separate worktree for each tool:

```bash
# Create temp directory for worktrees
WORKTREE_BASE=$(mktemp -d)

# Create worktree for each tool
git worktree add $WORKTREE_BASE/bandit -b janitor/bandit
git worktree add $WORKTREE_BASE/mypy -b janitor/mypy
# ... etc
```

### 2. Launch Parallel Subagents

Spawn one subagent per tool/worktree. Each subagent must:

1. Navigate to its worktree
2. Run its assigned quality tool
3. **Fix every issue found** (not just report)
4. Group fixes into small, logical commits
5. Use clear commit messages: `fix(<tool>): <description>`

### 3. Wait for Completion

Monitor all subagents until complete. Track:
- Which tools finished
- How many issues fixed per tool
- Any failures or blockers

### 4. Merge Results

Merge each subagent's commits into the target branch:

```bash
# Switch to target branch
git checkout <target-branch>

# Merge each tool's fixes
git merge janitor/bandit --no-ff -m "chore(quality): merge bandit fixes"
git merge janitor/mypy --no-ff -m "chore(quality): merge mypy fixes"
# ... etc
```

Preserve small logical commits (use merge or cherry-pick, not squash).

### 5. Resolve Conflicts

If merge conflicts occur:
- Understand both changes
- Preserve the intent of both fixes
- Test the resolution
- Continue with remaining merges

### 6. Cleanup

Remove worktrees when finished:

```bash
git worktree remove $WORKTREE_BASE/bandit
git worktree remove $WORKTREE_BASE/mypy
# ... etc

# Delete temporary branches
git branch -d janitor/bandit janitor/mypy # ... etc
```

### 7. Final Validation

```bash
# Run all quality checks to confirm
uv run pytest
uv run pre-commit run --all-files
npm test
npm run lint
```

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| Worktree creation fails | Dirty working tree | Commit or stash changes first |
| Subagent fails | Tool error | Check tool output, fix manually if needed |
| Merge conflict | Overlapping fixes | Resolve conflict, prioritize correctness |
| Tests fail after merge | Conflicting fixes | Debug, may need to revert and re-run |

## Success Criteria

- All quality tools run successfully
- All issues fixed (not just reported)
- Clean commit history with logical grouping
- All merges complete without unresolved conflicts
- Final validation passes
