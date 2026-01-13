# Generate Tests

Generate comprehensive tests for the codebase, including unit tests and end-to-end browser tests.

## When to Use

- When test coverage is low or missing
- After implementing new features
- When refactoring code that lacks tests

## Arguments

Usage: `/gen-tests [target] [--type unit|e2e|all]`

- `target` - Directory or module to generate tests for (default: auto-detect)
- `--type` - Type of tests to generate (default: all)

If `$ARGUMENTS` is provided, use it as the target path or options.

## Prerequisites

- For Python: pytest, pytest-cov, pytest-playwright (for E2E)
- For JavaScript: vitest or jest, playwright (for E2E)

## Steps

### 1. Detect Project Type and Analyze Coverage

**For Python projects:**
```bash
uv run pytest --collect-only 2>/dev/null || echo "No tests found"
uv run pytest --cov=. --cov-report=term-missing --cov-report=html
```

**For JavaScript/TypeScript projects:**
```bash
npm test -- --coverage 2>/dev/null || echo "No tests or coverage not configured"
npx vitest run --coverage
```

Identify untested or under-tested modules by reviewing the coverage report.

### 2. Generate Unit Tests

For each module or function lacking coverage:

1. **Analyze the code** - Understand inputs, outputs, side effects, and edge cases
2. **Create test file** - Follow naming conventions:
   - Python: `tests/test_<module_name>.py`
   - JavaScript: `<module>.test.ts` or `__tests__/<module>.test.ts`

3. **Write tests covering:**
   - Happy path scenarios
   - Edge cases (empty inputs, boundary values, null/None handling)
   - Error conditions and exception handling
   - Mocked external dependencies (APIs, databases, file I/O)

4. **Use fixtures/utilities** for common setup in `conftest.py` or test helpers

**Python example:**
```python
import pytest
from module import function_under_test

class TestFunctionUnderTest:
    def test_returns_expected_for_valid_input(self):
        result = function_under_test("valid")
        assert result == "expected"

    def test_raises_error_for_invalid_input(self):
        with pytest.raises(ValueError):
            function_under_test(None)
```

**JavaScript example:**
```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { functionUnderTest } from './module';

describe('functionUnderTest', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should return expected result for valid input', () => {
    const result = functionUnderTest('valid');
    expect(result).toBe('expected');
  });

  it('should throw error for invalid input', () => {
    expect(() => functionUnderTest(null)).toThrow();
  });
});
```

### 3. Generate E2E Browser Tests

If the project has web routes or UI components:

1. **Create E2E test directory:** `tests/e2e/`

2. **Write E2E tests:**

**Python (pytest-playwright):**
```python
import pytest
from playwright.sync_api import Page

def test_user_flow(page: Page):
    page.goto('/')
    page.click('[data-testid="button"]')
    assert page.locator('.result').is_visible()
```

**JavaScript (Playwright):**
```typescript
import { test, expect } from '@playwright/test';

test.describe('Feature', () => {
  test('should complete user flow', async ({ page }) => {
    await page.goto('/');
    await page.click('[data-testid="button"]');
    await expect(page.locator('.result')).toBeVisible();
  });
});
```

3. **Run E2E tests:**
```bash
# Python
uv run pytest tests/e2e/ --headed

# JavaScript
npx playwright test --headed
```

### 4. Increase Coverage

1. Review the coverage report
2. Focus on:
   - Lines marked as uncovered
   - Branches not taken
   - Functions with 0% coverage
3. Add targeted tests for gaps
4. Re-run coverage until target is met (aim for 80%+)

### 5. Validate All Tests Pass

**Python:**
```bash
uv run pytest -v --tb=short
uv run pytest --cov=. --cov-fail-under=70
```

**JavaScript:**
```bash
npm test
npx vitest run --coverage
npx playwright test
```

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| Import errors in tests | Missing test dependencies | Install pytest-cov, vitest, etc. |
| Flaky E2E tests | Timing issues | Add proper waits, use `expect` with retries |
| Mock not working | Wrong import path | Mock at the point of use, not definition |

## Guidelines

- **Mock external dependencies** - API calls, databases, browser APIs
- **Keep tests fast** - Mock slow external services
- **One assertion focus per test** when practical
- **Use descriptive test names:** `test_<function>_<scenario>_<expected_result>`
- **Parametrize repetitive tests** using `@pytest.mark.parametrize` or `test.each()`
- **Mark slow tests** with `@pytest.mark.slow` or tags so they can be skipped

## Success Criteria

- Test coverage increased to target level (70%+ minimum, 80%+ ideal)
- All new tests pass
- No flaky tests introduced
- Critical paths have E2E coverage
