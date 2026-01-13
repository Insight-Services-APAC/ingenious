# Verify CLAUDE.md Accuracy

Audit CLAUDE.md to ensure it accurately reflects the current state of the codebase.

## When to Use

- After significant codebase changes
- When onboarding to a new project
- During periodic documentation reviews

## Arguments

Usage: `/verify-claude-md [claude-md-path]`

- `claude-md-path` - Path to CLAUDE.md file (default: ./CLAUDE.md)

If `$ARGUMENTS` is provided, use it as the file path.

## Steps

### 1. Read Current CLAUDE.md

Read and understand all instructions in the CLAUDE.md file.

### 2. Verify Each Section

**Repository Context:**
- Does the description match actual project purpose?
- Is the project structure accurate?

**Package Management:**
```bash
# Check which package manager is used
ls pyproject.toml uv.lock package.json pnpm-lock.yaml yarn.lock requirements.txt 2>/dev/null
```

**Build/Run Commands:**
- Test each documented command
- Verify they execute successfully

**File Structure:**
- Check that documented paths exist
- Verify directory structure matches description

**Dependencies:**
- Confirm mentioned tools are in dependency files
- Check version requirements are current

**Configuration:**
- Verify config files exist
- Check that documented settings match actual files

### 3. Scan for Missing Context

Identify important aspects not documented:

**Entry Points:**
- Main files, scripts, or commands
- How to run the application

**Testing:**
- How to run tests
- Test frameworks used

**Environment Setup:**
- Required environment variables
- .env file requirements

**Key Patterns:**
- Architectural patterns used
- Coding conventions

**External Services:**
- APIs, databases, or services used

### 4. Check for Outdated Information

Look for:
- References to deleted files or directories
- Deprecated commands or workflows
- Old dependency versions
- Obsolete configuration instructions

### 5. Update CLAUDE.md

Fix any inaccuracies found:
- Remove outdated information
- Add missing critical context
- Update changed commands
- Correct file paths

### 6. Validate Changes

After updates, verify:
- All documented commands execute successfully
- All referenced paths exist
- Instructions are clear and actionable

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| Command fails | Outdated or wrong command | Update to correct command |
| Path not found | File moved or deleted | Update path or remove reference |
| Missing context | Documentation gap | Add necessary information |

## Success Criteria

- All documented commands work
- All referenced paths exist
- No outdated information remains
- Missing critical context added
- CLAUDE.md accurately reflects codebase
