# Fix State: Implement the Approved Fix

You are in the fix stage. The investigation is complete and a fix has been approved. Your job is to implement the fix correctly and safely.

## Principles of Minimal Fixes

- Make the smallest change that resolves the issue
- Do not refactor unrelated code
- Do not change formatting or style unless necessary
- Preserve existing behavior for all other cases
- If the fix feels large, reconsider if you understand the root cause

## Before You Start

1. Read the investigation findings from previous context
2. Understand the root cause clearly
3. Identify the exact files and lines that need modification
4. Consider if there are multiple valid fix approaches

## Implementation Steps

1. Create a new branch for your fix:
   ```bash
   git checkout -b fix/{{ issue.identifier }}-brief-description
   ```

2. Make the minimal code changes needed

3. Add or update tests that would have caught this bug:
   - Write a failing test first if tests exist
   - Apply your fix
   - Verify the test passes

4. Run the existing test suite to ensure no regressions:
   ```bash
   # Run relevant tests
   pytest tests/ -v -k "related_keyword"

   # Run full suite if changes are broad
   pytest tests/ -v
   ```

## Branch Naming Convention

Use the format: `fix/{{ issue.identifier }}-brief-kebab-description`

Examples:
- `fix/ENG-123-null-pointer-checkout`
- `fix/ENG-456-timeout-retry-logic`

## PR Description Format

When creating the PR, use this template:

```markdown
## Summary
Brief description of the bug and fix.

## Root Cause
One sentence explaining why the bug occurred.

## Changes Made
- File1: description of change
- File2: description of change

## Testing
- [ ] Added test case in `test_file.py`
- [ ] Existing tests pass
- [ ] Manual verification steps

Fixes {{ issue.identifier }}
```

Create the PR/MR with:
```bash
# GitHub
gh pr create --title "fix: brief description" --body "..." --base main

# GitLab
glab mr create --title "fix: brief description" --description "..." --target-branch main
```

## Completion Criteria

Mark this task complete when:
1. The fix is implemented and tested
2. A PR is opened with proper description
3. All tests pass (existing + new)
4. The Linear issue is moved to the appropriate review state

Do not wait for PR review approval before completing this state.
