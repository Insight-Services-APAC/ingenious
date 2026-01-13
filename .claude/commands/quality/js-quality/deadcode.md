# Find and Remove Dead Code with Knip

Use Knip to detect unused exports, dependencies, and dead code in JavaScript/TypeScript projects.

## When to Use

- During codebase cleanup
- Before major refactoring
- To reduce bundle size and maintenance burden

## Arguments

Usage: `/knip [target]`

- `target` - Directory to analyze (default: current directory with package.json)

If `$ARGUMENTS` is provided, use it as the target path.

## Prerequisites

- knip: `npm install -D knip`

## Steps

### 1. Install Knip (if missing)

```bash
npm install -D knip
```

### 2. Run Dead Code Analysis

```bash
npx knip
```

For more verbose output:
```bash
npx knip --include files,exports,types,duplicates
```

### 3. What Knip Detects

| Finding | Description |
|---------|-------------|
| Unused files | Files not imported anywhere |
| Unused exports | Exported items not imported elsewhere |
| Unused dependencies | Packages in package.json not used |
| Unused devDependencies | Dev packages not referenced |
| Unlisted dependencies | Used but not in package.json |
| Duplicate exports | Same thing exported multiple times |

### 4. Verify Each Finding

For each item detected, cross-check references:

**Check for indirect usage:**
- Dynamic imports: `import()`, `require()`
- String-based access: `components[name]`
- Vue/React template references
- Config file references (vite.config.ts, etc.)
- Test file usage
- Entry points in build config
- Plugin registrations
- Global component registration
- Runtime computed property access

### 5. Remove Verified Dead Code

**If certain the code is unused:**

```bash
# Remove unused dependency
npm uninstall <package-name>

# Or remove unused file/export manually
```

### 6. Test After Each Removal

```bash
npm run build 2>/dev/null || npm run build:check 2>/dev/null || true
npm test
```

### 7. Commit Incrementally

```bash
git add .
git commit -m "chore(cleanup): remove unused <item>"
```

### 8. Configure Knip

Create `knip.json` for project-specific settings:
```json
{
  "entry": ["src/main.ts", "src/index.ts"],
  "project": ["src/**/*.{ts,tsx,vue}"],
  "ignore": ["**/*.d.ts", "**/test/**"],
  "ignoreDependencies": ["@types/*"]
}
```

For monorepos:
```json
{
  "workspaces": {
    "packages/*": {
      "entry": ["src/index.ts"]
    }
  }
}
```

### 9. Final Validation

```bash
npx knip
npm run build
npm test
```

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| False positive on entry point | Not configured | Add to `entry` in knip.json |
| Plugin not detected as used | Dynamic registration | Add to `ignoreDependencies` |
| Build fails after removal | Code was actually used | Revert, investigate |

## Success Criteria

- Zero unused exports, files, or dependencies
- All removals tested and committed separately
- Build and tests pass
- knip.json configured for project specifics
