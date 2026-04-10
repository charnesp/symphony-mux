# Implement State

Your task is to implement the approved design in the workspace **up to the implementation-review gate**. Do **not** push to the remote or open a PR/MR from this stage — that happens later, when the workflow is ready for human **merge-review** (see `review-findings-route`).

## Implementation Guidelines

### Code Quality Standards

- Follow existing patterns in the codebase. Read similar files before writing new code.
- Use the same naming conventions, file organization, and architectural patterns you see.
- Keep functions focused and cohesive. Prefer composition over inheritance.
- Add type hints for function signatures and return values.
- Handle errors explicitly. Do not swallow exceptions without logging or reporting.
- Validate inputs at boundaries (API calls, file reads, user input).
- Avoid premature abstraction. Start concrete, extract patterns when repetition emerges.
- Document "why" in comments, not "what" (the code should explain what).

### Testing Requirements

All code changes must include tests:

**Unit Tests**
- Test individual functions in isolation
- Cover happy paths and error cases
- Mock external dependencies (HTTP, filesystem, time)
- Aim for clear test names that describe the scenario

**Integration Tests**
- Test component interactions end-to-end
- Verify database or API contract adherence
- Test actual subprocess calls where relevant
- Include at least one full workflow test

Run tests frequently: `uv run pytest tests/ -v`. You may use local `git commit` on a feature branch for your own checkpoints; do not push or open a PR/MR until the merge-review prep step.

### Documentation Requirements

- Update relevant docstrings if changing public APIs
- Update CLAUDE.md if changing architecture or design patterns
- Keep inline comments minimal but meaningful
- Ensure error messages are actionable for operators

## Quality checklist

Before marking complete, verify:

- [ ] Implementation matches the approved design
- [ ] All tests pass (`uv run pytest`)
- [ ] No new lint errors (`uv run ruff check`)
- [ ] Type checking passes (`uv run pyright`)
- [ ] Security scan clean (`uv run bandit -r stokowski/`)
- [ ] Local branch follows naming convention: `feature/description` or `fix/description` (for when the PR is opened later)
- [ ] Commit messages are clear and descriptive (local commits only)

## Local git (no push / no PR from this stage)

1. Work on a branch: `git checkout -b feature/your-change` (or continue the existing branch for this issue)
2. Make focused local commits with clear messages
3. **Do not** `git push` to open a remote branch for review yet
4. **Do not** open a PR/MR — that is done in the **merge-review prep** step (`review-findings-route` when routing `clean` or `needs_human`)

## Completion Criteria

Mark this task complete when:

1. All acceptance criteria from the design are implemented
2. Tests are written and passing
3. Changes are committed **locally** on the feature branch (ready for later push when merge-review prep runs)
4. No critical security or performance concerns remain

Do **not** merge. The next human gate is **implementation-review**; PR/MR creation waits until the workflow is ready for **merge-review**.

## Rework run

If this is a rework run after **implementation-review** requested changes:

1. Read the review feedback in Linear (and in your `<stokowski:report>` / issue thread context).
2. Address each point specifically on the existing local feature branch.
3. Run the full quality suite again.
4. Add new local commits (do not force-push). Implementation rework stays local until **`review-findings-route`** opens the PR for merge-review.

## Do NOT

- Create a new branch if one already exists for this issue
- Push to origin or open a PR/MR from this stage
- Force-push (use normal commits)
- Skip the quality suite (tests, lint, type-check)
- Merge
