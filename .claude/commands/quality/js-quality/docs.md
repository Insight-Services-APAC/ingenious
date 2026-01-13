# Verify and Fix JSDoc Comments

Use ESLint JSDoc plugin to ensure all functions, classes, and modules have proper documentation.

## When to Use

- When documentation coverage is low
- Before major releases
- When onboarding documentation is needed

## Arguments

Usage: `/jsdoc [target]`

- `target` - Directory or file to check (default: auto-detect JS/TS directories)

If `$ARGUMENTS` is provided, use it as the target path.

## Prerequisites

- ESLint configured
- eslint-plugin-jsdoc: `npm install -D eslint-plugin-jsdoc`

## Persistence Requirement

**DO NOT STOP until ALL JSDoc issues are resolved.** This task requires complete coverage:
- Process every single file reported by the tools
- Fix every missing or malformed JSDoc comment
- Continue working through all modules systematically
- Re-run the analysis tools after each batch of fixes
- Only consider complete when ESLint reports zero JSDoc violations

If context window limits approach, document remaining files in the todo list.

## Steps

### 1. Find JavaScript/TypeScript Source Directories

```bash
# Find directories with JS/TS files
find . -name "*.ts" -o -name "*.js" -o -name "*.vue" | grep -v node_modules | head -20
```

### 2. Install JSDoc Plugin (if missing)

```bash
npm install -D eslint-plugin-jsdoc
```

### 3. Configure ESLint

Add to ESLint config:
```javascript
{
  plugins: ['jsdoc'],
  extends: ['plugin:jsdoc/recommended-typescript'],
  rules: {
    'jsdoc/require-jsdoc': ['warn', {
      require: {
        FunctionDeclaration: true,
        MethodDefinition: true,
        ClassDeclaration: true,
        ArrowFunctionExpression: false,
        FunctionExpression: false
      }
    }],
    'jsdoc/require-description': 'warn',
    'jsdoc/require-param-description': 'warn',
    'jsdoc/require-returns-description': 'warn'
  }
}
```

### 4. Run JSDoc Analysis

```bash
npx eslint . --ext .js,.ts,.vue --rule 'jsdoc/require-jsdoc: warn'
```

### 5. JSDoc Standards

Use consistent JSDoc format:

```typescript
/**
 * Short one-line summary ending with period.
 *
 * Longer description if needed. Explain the purpose,
 * not the implementation.
 *
 * @param param1 - Description of first parameter.
 * @param param2 - Description of second parameter.
 * @returns Description of return value.
 * @throws {Error} When param2 is negative.
 *
 * @example
 * ```ts
 * const result = functionName('value', 42);
 * ```
 */
function functionName(param1: string, param2: number): boolean {
  // ...
}
```

For classes:
```typescript
/**
 * Short one-line summary.
 *
 * Longer description of the class purpose and usage.
 */
class ClassName {
  /** Description of property. */
  propertyName: string;

  /**
   * Creates an instance of ClassName.
   * @param config - Configuration options.
   */
  constructor(config: Config) {
    // ...
  }
}
```

### 6. Processing Order

Work through files systematically:
1. Public API functions and classes
2. Complex functions in components
3. Store actions and getters
4. Utility functions and helpers
5. Internal/private functions

### 7. Fix Iteratively

For each file with issues:
1. Add missing JSDoc comments
2. Fix style violations
3. Verify changes:
   ```bash
   npx eslint <file> --ext .ts,.vue
   ```
4. Commit when passing:
   ```bash
   git add <file>
   git commit -m "docs(<module>): add JSDoc to <file>"
   ```

### 8. Validate Coverage Improvement

After each batch:
```bash
npx eslint . --ext .js,.ts,.vue
npm test
```

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| TypeScript conflicts | JSDoc types vs TS types | Use `plugin:jsdoc/recommended-typescript` |
| Too many warnings | Large codebase | Process file by file |
| Vue SFC issues | Component structure | Focus on script section |

## Success Criteria

- Zero JSDoc ESLint violations
- All public functions have JSDoc comments
- All tests pass
- Documentation follows consistent style
