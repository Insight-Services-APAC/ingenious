# Refactor Using Complexity Analysis

Use ESLint complexity rules to identify and refactor high-complexity functions.

## When to Use

- When code is difficult to understand or modify
- Before major feature additions
- To improve code quality metrics

## Arguments

Usage: `/complexity [target] [--threshold number]`

- `target` - Directory or file to analyze (default: auto-detect JS/TS directories)
- `--threshold` - Maximum complexity allowed (default: 10)

If `$ARGUMENTS` is provided, use it as the target path.

## Prerequisites

- ESLint configured in the project

## Steps

### 1. Find JavaScript/TypeScript Source Directories

```bash
# Find directories with JS/TS files
find . -name "*.ts" -o -name "*.js" -o -name "*.vue" | grep -v node_modules | head -20
```

### 2. Run Complexity Analysis

```bash
# Check cyclomatic complexity
npx eslint . --ext .js,.ts,.vue --rule 'complexity: ["warn", 10]'
```

### 3. Identify Hotspots

Target functions with:
- Cyclomatic complexity > 10
- Many branches (if/else, switch)
- Deep nesting levels (> 3)
- High cognitive complexity

### 4. Configure ESLint Rules

Add to ESLint config:
```javascript
{
  rules: {
    'complexity': ['warn', { max: 10 }],
    'max-depth': ['warn', 4],
    'max-nested-callbacks': ['warn', 3],
    'max-lines-per-function': ['warn', { max: 50 }]
  }
}
```

### 5. Refactor Tactics

Apply one tactic at a time:

- **Extract function** for cohesive logic blocks
- **Guard clauses** replace nested conditionals with early returns
- **Object lookup maps** replace switch statements
- **async/await** replace nested callbacks
- **Decompose by responsibility** split large functions
- **Named predicates** extract complex conditions into functions
- **Strategy pattern** for variant behavior
- **Split components** with multiple concerns

After each change:
```bash
npm test
npx eslint <target_file> --rule 'complexity: ["error", 10]'
```

Commit if passing:
```bash
git add <files>
git commit -m "refactor(complexity): reduce complexity in <function>"
```

### 6. Validate No Regression

When a file is improved:
```bash
npx eslint . --ext .js,.ts,.vue
npm test
npm run build 2>/dev/null || npm run build:check 2>/dev/null || true
```

### 7. Know When to Stop

Stop when:
- Complexity <= 10
- Max nesting <= 3
- Function length reasonable
- Further splitting reduces readability

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| Tests fail after refactor | Behavior changed | Revert, write more tests first |
| Complexity stays high | Algorithm inherently complex | Document, add tests, accept |
| Type errors after split | Context lost | Ensure proper typing on extracted functions |

## Success Criteria

- No functions with cyclomatic complexity > 10
- Max nesting depth <= 4
- All tests pass
- Code is more readable
