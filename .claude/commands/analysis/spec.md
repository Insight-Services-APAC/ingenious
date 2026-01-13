# Create Test Specification

Generate a comprehensive specification file documenting all testable user stories in the application.

## When to Use

- Before starting E2E test development
- When documenting application features
- To create a testing roadmap

## Arguments

Usage: `/create-spec [target] [--output filename]`

- `target` - Directory or application to analyze (default: current project)
- `--output` - Output filename (default: spec.md)

If `$ARGUMENTS` is provided, use it as the target path or output file.

## Steps

### 1. Analyze the Codebase

Explore the application to identify all user-facing features:

**For web applications:**
- Routes and pages
- Forms and user inputs
- Navigation flows
- Authentication/authorization
- CRUD operations
- API endpoints

**For CLI applications:**
- Commands and subcommands
- Input/output behavior
- Configuration options

### 2. Document User Stories

Create `spec.md` with the following structure:

```markdown
# Application Test Specification

## Overview
Brief description of the application and its purpose.

## User Stories

### Feature: [Feature Name]

#### US-001: [User Story Title]
**As a** [user type]
**I want to** [action]
**So that** [benefit]

**Acceptance Criteria:**
- [ ] Criterion 1
- [ ] Criterion 2

**Test Scenarios:**
1. Happy path: [description]
2. Edge case: [description]
3. Error case: [description]

**Testable with Playwright:** Yes/No
```

### 3. Focus on Playwright-Testable Features

Include only features that can be tested via browser automation:
- Page navigation
- Form submissions
- Button clicks
- Content verification
- Modal interactions
- File uploads/downloads
- Authentication flows

### 4. Document Existing Features Only

**Do NOT add speculative features.** Only document functionality that exists in the current codebase:
- Check route definitions
- Review component implementations
- Verify API endpoints exist
- Confirm UI elements are rendered

### 5. Organize by Priority

Group user stories by:
1. Critical path (authentication, core features)
2. Primary features (main functionality)
3. Secondary features (nice-to-have)
4. Edge cases and error handling

## Output Format

The spec.md file should include:
- Clear user story identifiers (US-001, US-002, etc.)
- Testable acceptance criteria
- Mapping to actual UI elements (data-testid attributes)
- Prerequisites for each test scenario
- Expected outcomes

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| Feature unclear | Code is ambiguous | Read implementation, add TODO for clarification |
| No UI for feature | Backend-only functionality | Mark as "API test only" |
| Dynamic content | Content varies | Document expected patterns |

## Success Criteria

- All existing features documented
- Each user story has clear acceptance criteria
- Playwright-testable scenarios identified
- No speculative or non-existent features included
- spec.md is well-organized and readable
