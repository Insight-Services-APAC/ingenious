# Honest Code Review

Perform a direct, no-nonsense code review without diplomatic softening.

## When to Use

- Before merging significant changes
- When reviewing critical code paths
- To get unfiltered feedback on code quality

## Arguments

Usage: `/honest-review [target]`

- `target` - File, directory, or commit range to review (default: uncommitted changes)

If `$ARGUMENTS` is provided, use it as the review target.

## Steps

### 1. Identify Review Scope

```bash
# Review uncommitted changes
git diff

# Review staged changes
git diff --cached

# Review specific commit range
git diff <base>..<head>

# Review specific file
git diff <file>
```

### 2. Evaluate Against Criteria

**Correctness**
- Does this code actually work?
- Are there edge cases that will break it?
- Are there logic errors or off-by-one mistakes?
- Will this fail silently or produce wrong results?

**Design Problems**
- Is this the wrong approach entirely?
- Is this over-engineered for what it does?
- Is this under-engineered and will cause problems later?
- Does this duplicate existing functionality?

**Code Quality**
- Is this code hard to read or understand?
- Are the names misleading or unclear?
- Is the structure confusing?
- Would you struggle to debug this at 3am?

**Security and Reliability**
- Are there obvious security holes?
- Will this break under load or unusual conditions?
- Are errors handled properly or swallowed?

**Maintenance Burden**
- Will future developers curse this code?
- Is this adding unnecessary complexity?
- Does this violate established patterns in the codebase?

### 3. Output Format

Be direct. No praise sandwiches. No "great job but...". State issues plainly.

```
CRITICAL: [Issues that must be fixed before merge]
- The SQL query on line 45 is vulnerable to injection.

PROBLEM: [Issues that should be fixed but won't cause immediate harm]
- The function `processData` does three unrelated things.

CONCERN: [Items worth discussing or reconsidering]
- This adds a new dependency for something achievable with stdlib.

VERDICT: APPROVE | NEEDS CHANGES | REJECT
[One-line summary of the review outcome]
```

### 4. Be Accurate, Not Thorough-Looking

Do not add false positives to appear thorough. If the code is genuinely good, say so briefly and move on:

```
No significant issues found. Code is clear, handles edge cases, and follows existing patterns.

VERDICT: APPROVE
```

## Guidelines

- **State facts, not feelings** - "This function is 200 lines" not "This feels too long"
- **Be specific** - Include file:line references
- **Explain why** - Not just what's wrong, but why it matters
- **Suggest fixes** - When possible, indicate how to resolve issues
- **Prioritize** - Critical issues first, minor concerns last

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| No changes to review | Empty diff | Check branch, staging area |
| Too much to review | Large PR | Focus on changed files, suggest splitting |
| Unfamiliar domain | Specialized code | Note uncertainty, focus on general quality |

## Success Criteria

- All critical issues identified
- Clear actionable feedback provided
- Honest assessment without unnecessary harshness
- Verdict accurately reflects code quality
