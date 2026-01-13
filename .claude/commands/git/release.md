# Version Bump and Release

Increment version, create PR, merge, and publish release.

## When to Use

- When ready to release new version
- After features/fixes merged to main
- For scheduled releases

## Arguments

Usage: `/version-bump [bump-type] [--version x.y.z]`

- `bump-type` - Type of bump: patch, minor, major (default: patch)
- `--version` - Explicit version to set (overrides bump-type)

If `$ARGUMENTS` is provided, use it as bump type or version.

## Steps

### 1. Detect Current Version

Find version in:
- `pyproject.toml` (version field)
- `package.json` (version field)
- `src/__init__.py` or `<package>/__init__.py` (`__version__`)
- Other files with version strings

```bash
# Python
grep -E "^version\s*=" pyproject.toml
grep "__version__" **/__init__.py 2>/dev/null

# JavaScript
grep '"version"' package.json
```

### 2. Calculate New Version

Based on semantic versioning (vX.Y.Z):
- **patch** (Z+1): Bug fixes, minor changes
- **minor** (Y+1, Z=0): New features, backward compatible
- **major** (X+1, Y=0, Z=0): Breaking changes

Example: v0.2.7 -> v0.2.8 (patch)

### 3. Update All Version References

Replace old version with new in all identified files:
- pyproject.toml
- package.json
- __init__.py files
- Any other version references

### 4. Verify Changes

```bash
git diff
```

Confirm all version references updated correctly and consistently.

### 5. Create Version Bump PR

```bash
git checkout -b version-bump-vX.Y.Z
git add .
git commit -m "chore: bump version to vX.Y.Z"
git push -u origin version-bump-vX.Y.Z

gh pr create --base main --title "Bump version to vX.Y.Z" --body "Update version from vX.Y.Z to vX.Y.Z across all files"
```

### 6. Merge PR

Run quality checks and merge:

```bash
gh pr merge --merge --admin
```

### 7. Prepare Release Notes

Analyze changes since last release:

```bash
# Find previous version tag
git describe --tags --abbrev=0

# See commits since last release
git log <previous-tag>..HEAD --oneline

# See changed files
git diff <previous-tag>..HEAD --stat
```

Categorize into:
- Features
- Improvements
- Bug Fixes
- Documentation
- Internal changes

### 8. Create GitHub Release

```bash
gh release create vX.Y.Z \
  --title "Release vX.Y.Z" \
  --notes "$(cat <<'EOF'
## Summary
<Brief overview>

## Changes

### Features
- <feature>

### Improvements
- <improvement>

### Bug Fixes
- <fix>

### Documentation
- <doc change>

### Internal
- <internal change>

## Breaking Changes
<Note any breaking changes or "None">
EOF
)" \
  --target main
```

### 9. Verify Release

```bash
# Check release created
gh release view vX.Y.Z

# Monitor CI/CD if applicable
gh run list --limit 1
gh run watch
```

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| Version not found | Unusual location | Search manually, add to version files |
| Quality checks fail | Test/lint issues | Fix before proceeding to release |
| Release workflow fails | CI/CD issue | Check workflow logs |

## Guidelines

- Update ALL version references consistently
- Maintain version format (with/without 'v' prefix)
- No emojis in commits or release notes
- No attribution footers
- Verify quality before release

## Success Criteria

- All version references updated
- PR created and merged
- GitHub release published
- Release notes comprehensive
- CI/CD completed successfully
