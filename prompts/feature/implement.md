# Implement State

Your task is to implement the approved design and bring it to completion through a pull request.

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

Run tests before committing: `uv run pytest tests/ -v`

### Documentation Requirements

- Update relevant docstrings if changing public APIs
- Update CLAUDE.md if changing architecture or design patterns
- Keep inline comments minimal but meaningful
- Ensure error messages are actionable for operators

## PR Checklist

Before marking complete, verify:

- [ ] Implementation matches the approved design
- [ ] All tests pass (`uv run pytest`)
- [ ] No new lint errors (`uv run ruff check`)
- [ ] Type checking passes (`uv run pyright`)
- [ ] Security scan clean (`uv run bandit -r stokowski/`)
- [ ] Branch follows naming convention: `feature/description` or `fix/description`
- [ ] Commit messages are clear and descriptive
- [ ] PR description explains what and why, references Linear issue

## Git Workflow

1. Create a branch from main: `git checkout -b feature/your-change`
2. Make focused commits with clear messages
3. Push branch: `git push -u origin feature/your-change`
4. Open PR/MR:
   ```bash
   # GitHub
   gh pr create --title "..." --body "..."

   # GitLab
   glab mr create --title "..." --description "..."
   ```
5. Link PR/MR to Linear issue in description: `Closes TEAM-123`

## Completion Criteria

Mark this task complete when:

1. All acceptance criteria from the design are implemented
2. Tests are written and passing
3. PR is opened and linked to the Linear issue
4. CI checks pass (if configured)
5. No critical security or performance concerns remain

Do NOT merge the PR yourself. Leave it in review state for human approval.

## Rework run

If this is a rework run (a branch and PR already exist):

1. Find the existing PR/MR:
   ```bash
   # GitHub
   gh pr list --head <branch-name>

   # GitLab
   glab mr list --source-branch <branch-name>
   ```
2. Read review comments and requested changes:
   ```bash
   # GitHub
   gh pr view <number> --comments

   # GitLab
   glab mr view <number> --comments
   ```
3. Address each piece of feedback specifically.
4. Run the full quality suite again.
5. Push new commits to the existing branch (do not force-push).
6. Post a comment on the PR/MR summarising the rework:
   - Which review comments were addressed
   - What was modified
   - Any decisions or trade-offs
7. Append a rework section to the Linear tracking comment.

## Do NOT

- Create a new branch if one already exists for this issue
- Open a second PR when one already exists
- Force-push to the existing branch (use normal commits)
- Skip the quality suite (tests, lint, type-check)
- Merge your own PR without review approval
- Leave the PR unlinked to the Linear issue
