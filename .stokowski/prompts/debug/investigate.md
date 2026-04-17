# Investigation Stage

Your goal is to understand the bug described in the issue and identify its root cause. Do not fix the bug yet — only investigate and document your findings.

**No OpenSpec** for debug — do not create `openspec/changes/` artifacts.

## Step 1: Reproduce the bug

Before reading code, attempt to reproduce the issue:

1. Read the issue description carefully for:
   - Error messages or stack traces
   - Specific inputs or conditions that trigger the bug
   - Expected vs actual behavior

2. If reproduction steps are provided, follow them exactly
3. If the bug is environmental, note the conditions needed
4. If you cannot reproduce, document what you tried and why it may not manifest

## Step 2: Code reading strategy

Once you understand the symptoms, read code strategically:

1. **Start from the error** — If there's a stack trace, read bottom-up from the entry point
2. **Identify the subsystem** — Map the bug to specific modules/functions
3. **Trace data flow** — Follow how data moves from input to the failure point
4. **Check recent changes** — Look at git history for related modifications (`git log --oneline -20 -- <relevant-files>`)
5. **Read tests** — Existing tests reveal expected behavior and edge cases

Focus on understanding *why* the code behaves incorrectly, not just *what* is wrong.

## Step 3: Root cause vs symptoms

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

## Step 4: Investigation summary (inside `<stokowski:report>`)

Stokowski **extracts and posts only** the content between `<stokowski:report>` and `</stokowski:report>`. Put your investigation there — not as unstructured text outside the tags.

Use this structure (adapt **Technical Details** as needed):

```xml
<stokowski:report>
## Summary
- What you found (root cause in one line)
- Key evidence or uncertainty

## Commit Information

* **Branch:** `<git branch --show-current>` — optional tree URL
* **Commit SHA:** `<git rev-parse HEAD>` or `N/A — no commit yet on this branch` (rare)
* **Repository:** `<git remote get-url origin or group/project>`
* **MR URL:** `N/A — investigation stage; no MR`

## Technical Details

### Location
File and line numbers where the root cause exists.

### Root cause
One sentence describing the underlying flaw.

### Trigger condition
Specific input/state that causes the bug.

### Evidence
Short quotes or references to code/logs (plain Markdown — no JSON tool dumps).

### Risk assessment
Could fixing this cause regressions elsewhere?

## Files Changed
<!-- Investigation only: list paths you inspected, or "none" -->

## Approval Required
<!-- Required for fix-review gate: numbered items for the human reviewer -->

1. **[Root cause]:** Confirm the analysis before coding.
2. **[Fix scope]:** Confirm minimal fix approach (optional).
</stokowski:report>
```

Keep the investigation concise (aim under ~300 words in **Technical Details** unless the bug is genuinely complex). Do not paste stream-json, `tool_result` blobs, or line-number prefixes from IDE tools into the report.

## Transition criteria

Finish when:

- You have identified the root cause (not just symptoms)
- You can explain why a targeted fix will resolve the issue
- Edge cases or risks are noted
- Your `<stokowski:report>` is complete, including **Approval Required** for **fix-review**

Do **not** fix the bug in this stage. Do **not** create a PR.

## Rework run

If you are back here after **fix-review** rework:

1. Read the human feedback in Linear / recent comments.
2. Update your analysis; revise **Technical Details** and **Approval Required** in a new `<stokowski:report>`.
3. Do not skip straight to coding — this stage remains investigation-only.
