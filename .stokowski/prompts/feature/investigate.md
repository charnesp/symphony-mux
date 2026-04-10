# Investigation Phase

Your task is to thoroughly research this feature request before any implementation begins. You are an investigator, not a builder right now. Take time to understand the problem space deeply.

## OpenSpec (required)

Follow the **`openspec-propose`** skill (**`/openspec-propose`**). Do not re-document that workflow here — use the skill to create or continue the OpenSpec change and its artifacts under `openspec/changes/<name>/` as the skill specifies.

**This stage is still investigation-only:** read and explore the codebase as needed; **do not** implement product code or skip straight to coding in a later stage without that change in place.

## Your Mission

1. **Understand the requirements** by reading all available context
2. **Research existing patterns** in this codebase
3. **Design a minimal viable approach** and carry it through **`/openspec-propose`** (change name, artifacts)
4. **Document your findings** for human review (Linear summary below, consistent with the artifacts the skill produced)

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

### OpenSpec change
<!-- `openspec/changes/<name>/` produced or updated via `/openspec-propose` — link or name only -->

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
3. You have followed **`/openspec-propose`** so the OpenSpec change and required artifacts exist under `openspec/changes/<name>/`
4. You have posted a complete investigation summary as a Linear comment
5. Your summary includes specific files, functions, and a concrete plan
6. Any open questions are clearly documented

## Rework run

If this is a rework run (the workspace already has investigation content):

1. Read the review feedback from Linear comments.
2. Read your prior investigation summary.
3. Address the specific feedback — expand analysis, correct mistakes, or investigate additional areas as requested.
4. Update the `## Investigation` comment with revised findings.
5. Append a rework note to the Linear tracking comment.

## Do NOT

- Write implementation code
- Create branches or PRs
- Modify source files (reading is fine)
- Skip the investigation to jump straight to coding

Once posted, transition the issue to the "research-review" state and stop. A human will review your findings and either approve the approach or request clarification.
