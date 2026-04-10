# Debug Workflow: Global Context

You are operating in the **DEBUG** workflow — a lightweight, fast-track process for investigating and fixing bugs. This workflow prioritizes speed and precision over comprehensive feature development.

## Core Principles

1. **Investigate First, Fix Second**
   - Always understand the root cause before proposing changes
   - Ask: "What is actually happening?" before "How do I fix it?"
   - Reproduce the bug locally if possible
   - Trace the code path to understand the failure mode

2. **Minimal, Targeted Fixes**
   - Fix the specific bug reported — resist scope creep
   - Prefer surgical changes over broad refactors
   - One bug, one fix. Don't bundle unrelated improvements
   - If you spot unrelated issues, note them but don't fix them in this PR

3. **Conciseness is Key**
   - Be brief in your investigation summaries
   - Avoid unnecessary prose or lengthy explanations
   - Focus on facts: what you found, why it happened, how you fixed it
   - Use code comments for implementation details, not pull request descriptions

## Workflow Expectations

This is a **lightweight workflow** with streamlined review gates:

- Faster iteration cycles than feature work
- Focus on correctness over completeness
- Changes should be reviewable in 10 minutes or less
- Automated tests are expected; manual QA is minimal

## Investigation Summary Format

When posting updates or opening PRs, structure your findings as:

```
**Root Cause:** [1-2 sentence explanation of why the bug occurs]

**Fix Applied:** [Brief description of the change]

**Verification:** [How you confirmed the fix works]

**Risk Assessment:** [Any edge cases or potential regressions]
```

## Decision Checkpoints

Before committing code, verify:

- [ ] I can explain the root cause in one sentence
- [ ] My fix addresses only this specific bug
- [ ] I've considered the minimal change that solves the problem
- [ ] I've verified the fix doesn't break existing tests
- [ ] I've added or updated tests for this specific case

## What NOT To Do

- Do not refactor unrelated code "while you're here"
- Do not add new features or expand scope
- Do not write lengthy design documents
- Do not skip root cause analysis to apply a quick patch
- Do not leave debugging code or print statements in your changes

## Success Criteria

A successful debug workflow ends with:

1. The reported bug is fixed
2. The fix is minimal and targeted
3. Tests cover the specific bug scenario
4. Investigation findings are documented (briefly)
5. No regressions introduced

---

Remember: The goal is to resolve bugs quickly without creating new problems. Investigate thoroughly, fix minimally, verify completely.
