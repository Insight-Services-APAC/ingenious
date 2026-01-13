# Technical Debt Analysis

Perform deep manual analysis of the codebase to identify technical debt through comprehensive code reading.

## When to Use

- During planning for major refactoring
- Before taking on new team members
- To create a technical roadmap
- When code quality is declining

## Arguments

Usage: `/tech-debt-analysis [target]`

- `target` - Directory or module to analyze (default: entire project)

If `$ARGUMENTS` is provided, use it as the target path.

## Steps

### 1. Deep Code Reading

**Read every source file systematically:**
- Understand complete codebase structure
- Trace logic flow and execution paths
- Analyze data flow and transformations
- Map dependency relationships between modules

### 2. Architecture and Design Debt

**Identify:**
- Architectural inconsistencies (patterns not followed)
- SOLID principle violations (multiple responsibilities, tight coupling)
- Abstraction leaks (implementation details exposed)
- Missing abstractions (repeated patterns not extracted)
- Layering violations (inappropriate cross-layer dependencies)

### 3. Code Quality Issues

**Look for:**
- Complex functions/methods (hard to understand)
- Poor naming (confusing variable, function, class names)
- Code duplication (repeated logic to consolidate)
- Inconsistent patterns (similar problems solved differently)
- Magic numbers/strings (hardcoded values needing constants)

### 4. Maintainability Problems

**Find:**
- Commented-out code (dead code in comments)
- TODO/FIXME comments (deferred work, shortcuts)
- Brittle code (fragile implementations)
- Over-engineering (unnecessary complexity)
- Under-engineering (oversimplified, will break under load)

### 5. Business Logic Issues

**Identify:**
- Domain model inconsistencies
- Missing error handling
- Incomplete features (half-implemented functionality)
- Performance anti-patterns (inefficient algorithms)

### 6. Testing and Documentation Gaps

**Find:**
- Untestable code (tightly coupled, hard to test)
- Missing edge case handling
- Undocumented complex logic
- Inconsistent error messages

### 7. Security and Data Handling

**Check for:**
- Input validation gaps
- Information leakage
- Authentication/authorization inconsistencies
- Data integrity problems

### 8. Output Format

```markdown
# Technical Debt Analysis Report

## Executive Summary
[High-level findings and recommendations]

## Codebase Overview
[System architecture and main components]

## Critical Issues
[Most severe debt posing immediate risks]

| Issue | Location | Severity | Impact |
|-------|----------|----------|--------|
| [Description] | file:line | High/Medium/Low | [Business impact] |

## Systemic Problems
[Patterns of debt appearing throughout codebase]

## Module-by-Module Analysis

### [Module Name]
- Issues found
- Recommended fixes
- Effort estimate

## Refactoring Opportunities
[Concrete suggestions for improvement]

## Risk Assessment
[Impact analysis of identified debt]

## Recommended Roadmap
1. [Highest priority - address immediately]
2. [High priority - address soon]
3. [Medium priority - plan for]
4. [Low priority - address opportunistically]
```

### 9. Review Like a Senior Developer

Question every design decision:
- Why was this done this way?
- What edge cases are missing?
- How will this scale?
- Is this maintainable long-term?

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| Too much to analyze | Large codebase | Focus on core modules first |
| Unclear original intent | Missing documentation | Document assumptions, flag for review |
| Conflicting patterns | Multiple developers | Identify dominant pattern, recommend standardization |

## Success Criteria

- All major technical debt identified
- Issues prioritized by business impact
- Clear remediation roadmap provided
- Risk assessment completed
- Actionable recommendations given
