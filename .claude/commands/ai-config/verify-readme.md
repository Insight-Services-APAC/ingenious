# Verify README.md Accuracy

Audit README.md to ensure it accurately reflects the codebase and provides working instructions.

## When to Use

- After significant codebase changes
- Before releases
- During documentation reviews

## Arguments

Usage: `/verify-readme [readme-path]`

- `readme-path` - Path to README.md file (default: ./README.md)

If `$ARGUMENTS` is provided, use it as the file path.

## Steps

### 1. Read Current README.md

Read and understand all content in the README.md file.

### 2. Verify Each Section

**Project Description:**
- Does it accurately describe what the code does?
- Is the purpose clear?

**Prerequisites:**
```bash
# Check version requirements
node --version 2>/dev/null
python --version 2>/dev/null
go version 2>/dev/null
```

**Installation Commands:**
- Execute each installation step
- Verify it works without errors

**Run/Start Commands:**
- Verify the main execution command works
- Check that the application starts correctly

**Configuration:**
- Check documented config files exist
- Verify environment variables are accurate

**File Paths:**
- Verify all referenced directories and files exist

### 3. Test All Code Examples

For every code block in README.md:

1. Copy the exact command or code
2. Execute it in the project root
3. Verify it produces documented result
4. Note any errors or unexpected output

### 4. Check for Missing Essentials

**Environment Variables:**
```bash
# Find environment variable usage
grep -r "process.env\|os.environ\|os.Getenv" --include="*.js" --include="*.ts" --include="*.py" --include="*.go" . 2>/dev/null | head -20
```

**System Dependencies:**
- Are databases or services mentioned?
- Are system requirements documented?

**Port Numbers:**
- Are default ports documented?

**Common Errors:**
- Are known setup issues addressed?

### 5. Check for Outdated Information

Look for:
- References to removed files or deprecated features
- Old version numbers or requirements
- Broken links (internal and external)
- Commands that fail
- Screenshots that no longer match UI

**Check internal links:**
```bash
grep -oE '\[.*\]\((\.?/[^)]+)\)' README.md | grep -oE '\(.*\)' | tr -d '()' | while read path; do
  [ ! -e "$path" ] && echo "Broken: $path"
done
```

### 6. Verify External Links

Test all URLs in README.md:
- Documentation links
- External resources
- Badge URLs
- Repository links

### 7. Update README.md

Fix any inaccuracies:
- Correct broken commands
- Update version requirements
- Remove references to deleted files
- Add missing setup steps
- Fix broken links

### 8. Validate Changes

After updates, perform clean test:
1. Follow README instructions from scratch
2. Verify the project runs successfully
3. Document any additional steps needed

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| Command fails | Outdated syntax | Update command |
| Link broken | Resource moved | Update URL or remove |
| Version mismatch | Requirements changed | Update version numbers |

## Success Criteria

- All documented commands work
- All links resolve correctly
- New developer can go from clone to running
- No outdated information remains
