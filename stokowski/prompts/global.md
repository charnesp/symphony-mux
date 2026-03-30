# Global Agent Instructions

These instructions apply to every agent turn in this workflow.

## Pre-Completion Checklist

Before finalizing your response, you MUST verify:

- [ ] **Stokowski Report Included**: Have I included `<stokowski:report>...</stokowski:report>` tags in my response?
- [ ] **Report Structure Complete**: Does the report contain all required sections (Summary, Technical Details, Files Changed)?
- [ ] **Summary Present**: Did I summarize what was accomplished, key decisions, and any blockers?
- [ ] **Files Documented**: Did I list all files changed with brief descriptions?
- [ ] **Gate Requirements Met**: If transitioning to a gate state, did I include an "Approval Required" section?

## Response Format Rules

1. **ALWAYS end your response** with the XML report tags
2. **NEVER omit** the report - your work will be rejected without it
3. **Follow the exact format** specified in the lifecycle context
4. The report must be **valid XML** with proper opening and closing tags

## Why This Matters

The `<stokowski:report>` is extracted by the orchestrator and posted as a structured comment on the Linear issue. Without it, your work cannot be tracked or reviewed properly.
