# Implement State

Your task is to implement the approved design in the workspace **before automated code-review** (`code-review` state). Push commits to the existing feature branch on `origin`, but do **not** open a PR/MR from this stage — PR/MR handling happens later in `review-findings-route`.

## OpenSpec (required)

Follow the **`openspec-apply-change`** skill (**`/openspec-apply-change`**). Do not re-document that workflow here — use it to select the change, follow apply instructions, and complete `tasks.md` as the skill defines. If scope shifts, update the change artifacts before coding. **Do not** run **`openspec-archive-change`** from this stage; it runs in the **merge** state **before** the PR is merged (see `merge.md`).

## Strict TDD (required)

Follow **strict test-driven development** for all production code in this stage:

1. **RED** — Write a **failing** automated test that specifies the desired behavior (or reproduces the bug). Run it and confirm it fails for the **right** reason.
2. **GREEN** — Write the **minimal** production code to make that test pass. No extra features.
3. **REFACTOR** — Improve structure and readability while keeping tests green.

**Rules:**

- **Never** add or change production behavior without a failing test written (or updated) **first**, except trivial non-behavioral edits explicitly allowed by team convention.
- Every bugfix: test that fails before the fix, passes after.
- Prefer `npm run test` (or project-standard commands) after each small step.

## Implementation Guidelines

### Code Quality Standards

- Follow existing patterns in the codebase. Read similar files before writing new code.
- Use the same naming conventions, file organization, and architectural patterns you see.
- Keep functions focused and cohesive. Prefer composition over inheritance.
- Preserve and improve type safety using the project's conventions (TypeScript types where applicable, otherwise clear runtime validation at boundaries).
- Handle errors explicitly. Do not swallow exceptions without logging or reporting.
- Validate inputs at boundaries (API calls, file reads, user input).
- Avoid premature abstraction. Start concrete, extract patterns when repetition emerges.
- Document "why" in comments, not "what" (the code should explain what).

### Testing Requirements

TDD is mandatory (see **Strict TDD** above). In addition:

**Unit Tests**
- Test individual functions in isolation
- Cover happy paths and error cases
- Mock external dependencies (HTTP, filesystem, time)
- Aim for clear test names that describe the scenario

**Integration Tests**
- Test component interactions end-to-end
- Verify database or API contract adherence
- Test actual subprocess calls where relevant
- Include at least one full workflow test when behavior crosses boundaries

Run tests frequently: `npm run test`. Use normal commits on the feature branch and push them to `origin`; do not open a PR/MR until the merge-review prep step.

### Documentation Requirements

- Update relevant docs/comments if changing public APIs or behavior
- Update `AGENTS.md` and the relevant files in `docs/` if changing architecture or design patterns
- Keep inline comments minimal but meaningful
- Ensure error messages are actionable for operators

## Pre-commit (mandatory — full hook suite)

Before marking this stage complete, you **must** run the project's full local quality bar. That is the operator’s definition of “green”:

```bash
npm audit
npm run test
npm run lint
```

This covers dependency audit, tests, and lint checks expected by the frontend repo hooks. **Do not** bypass hooks with `git commit --no-verify` or claim done before all three commands are green. If any command fails, fix the underlying issue and re-run until all pass.

## Quality checklist

Before marking complete, verify:

- [ ] Implementation matches the approved design
- [ ] `npm audit`, `npm run test`, and `npm run lint` all pass
- [ ] Branch follows naming convention: `feature/description` or `fix/description`
- [ ] Branch exists on `origin` and latest commit is pushed
- [ ] Commit messages are clear and descriptive
- [ ] `<stokowski:report>` includes **`## Commit Information`** (four bullets with real `git` values), per **`## ⚠️ REQUIRED: Structured Work Report`** in your assembled instructions (find that heading)

## Local git (push allowed, no PR from this stage)

1. Work on a branch: `git checkout -b feature/your-change` (or continue the existing branch for this issue)
2. **Publish on `origin` with upstream:** If **`origin/<branch>` does not exist yet** or your local branch has **no upstream** tracking branch, run **once**:
   ```bash
   git push -u origin <branch>
   ```
   (`-u` / `--set-upstream` is required for the first push that creates the remote branch or links tracking.) If the remote branch already exists and upstream is set, skip this.
3. Make focused commits with clear messages, then push (`git push`). If `git push` fails because upstream is missing, use `git push -u origin <branch>` once.
4. **Do not** open a PR/MR — that is done in the **merge-review prep** step (`review-findings-route` when routing `clean` or `needs_human`)

## Completion Criteria

Mark this task complete when:

1. All acceptance criteria from the design are implemented
2. Tests are written and passing **and** `npm audit`, `npm run test`, and `npm run lint` pass
3. Changes are committed and pushed to `origin` on the feature branch
4. No critical security or performance concerns remain
5. `<stokowski:report>` includes the mandatory **`## Commit Information`** block (four bullets: Branch, Commit SHA, Repository, MR URL) filled from `git` — per **`## ⚠️ REQUIRED: Structured Work Report`** in your assembled instructions (find that heading; it may appear before or after this text).

Do **not** merge. After you finish, Stokowski advances to **code-review** (agent); PR/MR creation waits until the workflow is ready for **merge-review** (human gate).

Example for **`## Commit Information`**:

```markdown
## Commit Information

* **Branch:** `feature/your-change` — `https://gitlab.com/<group>/<project>/-/tree/<branch>`
* **Commit SHA:** `<output of git rev-parse HEAD>`
* **Repository:** `<git remote get-url origin or group/project>`
* **MR URL:** `N/A — MR not created until merge-review prep` (unless an MR already exists)
```

## Rework run

If this is a rework run (e.g. **merge-review** sent the issue back to **implement**, or similar):

1. Read the review feedback in Linear (and in your `<stokowski:report>` / issue thread context).
2. Address each point specifically on the existing local feature branch.
3. Run `npm audit`, `npm run test`, and `npm run lint` again and fix until all checks pass.
4. Add new commits and push updates to the same branch (do not force-push). Use `git push -u origin <branch>` if upstream is not set; otherwise `git push`.

## Do NOT

- Create a new branch if one already exists for this issue
- Open a PR/MR from this stage
- Force-push (use normal commits)
- Skip or bypass quality checks (`git commit --no-verify`, or stopping before running all of `npm audit`, `npm run test`, and `npm run lint`)
- Merge
