# Find and Fix TypeScript Errors

Use the TypeScript compiler to detect and fix type errors.

## When to Use

- Before committing TypeScript changes
- When adding types to JavaScript code
- To catch type-related bugs early

## Arguments

Usage: `/tsc [target]`

- `target` - Directory or tsconfig to check (default: current directory)

If `$ARGUMENTS` is provided, use it as the target path.

## Prerequisites

- TypeScript installed: `npm install -D typescript`
- tsconfig.json configured

## Steps

### 1. Run Type Check

```bash
npx tsc --noEmit
```

Or using the project's build script:
```bash
npm run build:check 2>/dev/null || npm run typecheck 2>/dev/null || npx tsc --noEmit
```

For specific tsconfig:
```bash
npx tsc --noEmit -p tsconfig.json
```

### 2. Review Output

For each error, note:
- File path and line number
- Error code (e.g., TS2339, TS7006)
- Error description

### 3. Common Errors and Fixes

| Error Code | Description | Fix |
|------------|-------------|-----|
| TS2339 | Property does not exist | Add to interface or use type assertion |
| TS7006 | Parameter has implicit any | Add explicit type annotation |
| TS2345 | Argument type mismatch | Fix the type or use type guard |
| TS2322 | Type not assignable | Ensure types are compatible |
| TS2531 | Object possibly null | Add null check or optional chaining |
| TS2532 | Object possibly undefined | Add undefined check |
| TS18046 | Unknown type | Add type narrowing |
| TS2307 | Cannot find module | Install types or add declaration |
| TS2304 | Cannot find name | Import or declare the type |

### 4. Fix Iteratively

For each error:
1. Understand the error and context
2. Update code to satisfy type checker
3. Re-run type check on specific file:
   ```bash
   npx tsc --noEmit <file>
   ```
4. Commit when clean:
   ```bash
   git add <file>
   git commit -m "fix(types): resolve TS<code> in <file>"
   ```

### 5. Configure Strict Mode

For stricter checking, ensure `tsconfig.json` includes:
```json
{
  "compilerOptions": {
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true,
    "noImplicitReturns": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "exactOptionalPropertyTypes": true
  }
}
```

### 6. Handle Third-Party Types

For packages without types:
```bash
# Install type definitions
npm install -D @types/package-name

# Or create declaration file
echo "declare module 'package-name';" > src/types/package-name.d.ts
```

### 7. Final Validation

```bash
npx tsc --noEmit
npm run build
npm test
```

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| Too many errors | Strict mode on JS migration | Start with `allowJs`, add types incrementally |
| Third-party type errors | Outdated @types package | Update or add to `skipLibCheck` |
| Generic type issues | Complex inference | Add explicit type parameters |

## Success Criteria

- Zero TypeScript errors with strict mode
- All type annotations accurate
- No `any` types without justification
- Build and tests pass
