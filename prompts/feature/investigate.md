# Investigation Phase

Your task is to thoroughly research this feature request before any implementation begins. You are an investigator, not a builder right now. Take time to understand the problem space deeply.

## Your Mission

1. **Understand the requirements** by reading all available context
2. **Research existing patterns** in this codebase
3. **Design a minimal viable approach**
4. **Document your findings** for human review

## Local git (local only — no push / no PR)

Do **not** do investigation work only on the repo default branch (`main` / `master`). Create a dedicated branch so later stages (`implement`, `review-findings-route`) reuse the same line of history.

**First run**

1. Update the base branch: `git fetch` and `git checkout` the default branch (usually `main`), then `git pull` as appropriate.
2. Create a work branch: `git checkout -b feature/<short-kebab-description>`. For bugfixes, use `fix/<short-kebab-description>`. You may include the issue identifier in the name (e.g. `feature/man-25-short-topic`). Use the same naming style as **`implement`**: `feature/description` or `fix/description`, kebab-case and descriptive.
3. Optional: make local commits on this branch as checkpoints; the investigation still must be posted to Linear as specified below.
4. **Do not** `git push` or open a PR/MR from this stage. Push and PR happen only when **`review-findings-route`** prepares merge-review.

**Rework run:** If a feature or fix branch already exists for this issue, stay on it; do not create a second branch.

## Codebase Exploration Strategy

Start broad, then narrow:

1. **Read the issue description completely** - note explicit requirements, constraints, and success criteria
2. **Examine related files** mentioned or implied by the issue
3. **Search for similar implementations** using `git grep` or file searches
4. **Check tests** - they reveal expected behavior and edge cases
5. **Review recent commits** - `git log --oneline -20` for context on current patterns

## Finding Similar Implementations

When researching patterns:
- Search for function/class names that sound related
- Look for files in similar directories - patterns cluster
- Check imports in related modules to find dependency patterns
- Read 2-3 similar implementations to understand conventions, not just one

Ask yourself:
- How do we typically handle this type of data?
- What error handling patterns are used?
- What testing approach is standard?
- Are there existing abstractions I should use?

## Design Document Structure

Post your investigation as a Linear comment with this structure:

```markdown
## Investigation Summary

### Requirements Understanding
<!-- What is the actual problem? What are the explicit vs implied requirements? -->

### Existing Patterns Found
<!-- What similar code exists? Link to files and explain the patterns discovered -->

### Proposed Approach
<!-- Your recommended implementation strategy. Be specific about:
- Files to create/modify
- Key functions/classes needed
- Dependencies to leverage -->

### Open Questions
<!-- What needs clarification before proceeding? Be specific -->

### Risk Assessment
<!-- What could go wrong? Dependencies, scope creep, unknown unknowns -->
```

## Decision Guidelines

**Ask for clarification when:**
- Requirements contradict existing patterns
- The scope is ambiguous or could be interpreted multiple ways
- Critical dependencies are unclear
- The issue description is incomplete or seems outdated

**Proceed with confidence when:**
- Similar implementations exist as clear templates
- The path forward is obvious from existing patterns
- Requirements are explicit and complete

## Completion Criteria

You are done investigating when:

1. You have read all relevant code in the codebase
2. You have identified 2-3 similar implementations as reference
3. You have posted a complete investigation summary as a Linear comment
4. Your summary includes specific files, functions, and a concrete plan
5. Any open questions are clearly documented

## Rework run

If this is a rework run (the workspace already has investigation content):

1. Read the review feedback from Linear comments.
2. Read your prior investigation summary.
3. Stay on the existing work branch; do not create a second branch.
4. Address the specific feedback — expand analysis, correct mistakes, or investigate additional areas as requested.
5. Update the `## Investigation` comment with revised findings.
6. Append a rework note to the Linear tracking comment.

## Do NOT

- Write implementation code
- **Push** to the remote or **open a PR/MR** from this stage
- Create a **second** branch if one already exists for this issue (rework)
- Modify source files (reading is fine)
- Skip the investigation to jump straight to coding

Once posted, transition the issue to the "research-review" state and stop. A human will review your findings and either approve the approach or request clarification.
