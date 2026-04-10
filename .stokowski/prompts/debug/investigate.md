# Investigation Stage

Your goal is to understand the bug described in the issue and identify its root cause. Do not fix the bug yet — only investigate and document your findings.

## Step 1: Reproduce the Bug

Before reading code, attempt to reproduce the issue:

1. Read the issue description carefully for:
   - Error messages or stack traces
   - Specific inputs or conditions that trigger the bug
   - Expected vs actual behavior

2. If reproduction steps are provided, follow them exactly
3. If the bug is environmental, note the conditions needed
4. If you cannot reproduce, document what you tried and why it may not manifest

## Step 2: Code Reading Strategy

Once you understand the symptoms, read code strategically:

1. **Start from the error** — If there's a stack trace, read bottom-up from the entry point
2. **Identify the subsystem** — Map the bug to specific modules/functions
3. **Trace data flow** — Follow how data moves from input to the failure point
4. **Check recent changes** — Look at git history for related modifications (`git log --oneline -20 -- <relevant-files>`)
5. **Read tests** — Existing tests reveal expected behavior and edge cases

Focus on understanding *why* the code behaves incorrectly, not just *what* is wrong.

## Step 3: Root Cause vs Symptoms

Distinguish between:

- **Symptom**: The visible error or incorrect output
- **Root cause**: The underlying logic flaw that produces the symptom

Common root cause patterns:
- Logic error in condition (using `and` instead of `or`, off-by-one)
- Missing null/edge case handling
- State mutation where immutability expected
- Incorrect assumption about input format
- Race condition or timing issue
- Configuration/default value mismatch

State the root cause as: "The bug occurs because [specific code/condition] fails to handle [specific scenario]"

## Step 4: Investigation Summary

Post a Linear comment with:

**Investigation Summary for [Issue Title]**

- **Location**: File and line numbers where the root cause exists
- **Root Cause**: One sentence describing the underlying flaw
- **Trigger Condition**: Specific input/state that causes the bug
- **Evidence**: Key code snippets or logs supporting your conclusion
- **Risk Assessment**: Could fixing this cause regressions elsewhere?

Keep the summary under 200 words. Link to specific commits or files using full paths.

## Transition Criteria

Move the issue to the "fix-review" state when:

- You have identified the root cause (not just symptoms)
- You can explain why the fix will resolve the issue
- You have noted any edge cases or risks to consider
- The investigation summary comment is posted

Do NOT attempt to fix the bug in this stage. The fix will be planned and reviewed separately.
