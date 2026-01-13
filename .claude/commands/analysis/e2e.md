# Autonomous Web App Validation

Work autonomously to validate the application end-to-end against all user stories in `spec.md`.

## When to Use

- After implementing features documented in spec.md
- For comprehensive E2E testing
- To validate application completeness

## Prerequisites

- `spec.md` must exist with documented user stories
- If missing, run `/create-spec` first
- Application must be running and accessible
- Playwright MCP or browser automation available

## Arguments

Usage: `/iteratively-verify [spec-file]`

- `spec-file` - Path to specification file (default: spec.md)

If `$ARGUMENTS` is provided, use it as the spec file path.

## Autonomous Work Expectations

- **Do not stop early** - Work until everything is complete
- **Do not stop** due to token budget concerns
- **Complete tasks fully**, even if end of budget is approaching
- **Never artificially stop** any task early

## Steps

### 1. Load Specification

Read `spec.md` and create a checklist of all user stories to validate.

### 2. Validation Cycle

For **each** user story in the specification:

1. **Validate** - Test the feature using browser automation
2. **Debug** - If issues found, identify root cause
3. **Implement** - Fix the code if needed
4. **Deploy** - Apply changes (restart server if necessary)
5. **Re-validate** - Confirm the fix works
6. **Mark Complete** - Update progress tracking
7. **Next** - Move to next user story

### 3. Development Workflow

After any code change:
1. Save the file
2. Restart/reload the application if needed
3. Re-test the functionality
4. Proceed only after confirming stability

Debug cycle: `Debug -> Fix -> Deploy -> Verify -> Repeat`

### 4. Validation Requirements

| Aspect | Details |
|--------|---------|
| Source | All user stories in spec.md |
| Coverage | Functional correctness, data flow, state transitions, error handling |

For each page/feature:
- All functions must work (no placeholders)
- All routes accessible via UI
- Data displays correctly
- Forms submit and validate properly
- Error states handled gracefully

### 5. Handling Unclear Specifications

If specifications are ambiguous:
- Check the actual implementation for intended behavior
- Document assumptions made
- Add clarifying notes to spec.md
- Preserve original intent

### 6. Execution Priorities

1. Complete **everything** in spec.md
2. Validate each feature thoroughly
3. Debug and fix issues immediately
4. Deploy after each fix
5. Do not stop until all stories pass

## Completion Criteria

Work is **not complete** until:
- Every user story in spec.md is validated
- Every feature passes its acceptance criteria
- Every bug found is fixed and verified
- The application works end-to-end

## Error Handling

| Issue | Cause | Resolution |
|-------|-------|------------|
| spec.md not found | Missing file | Run `/create-spec` first |
| Application not running | Server down | Start the application |
| Feature not implemented | Incomplete code | Implement the feature |
| Flaky test | Timing or state issue | Add proper waits, fix state management |

## Success Criteria

- All user stories in spec.md validated
- All acceptance criteria met
- No unresolved bugs
- Application fully functional
