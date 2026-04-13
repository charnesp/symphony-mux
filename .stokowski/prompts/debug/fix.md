# Fix State: Implement the Approved Fix

You are in the **debug** workflow **fix** stage. The investigation is complete and a human approved the approach at **fix-review**. Implement the fix correctly and safely.

**No OpenSpec** — do not create or update `openspec/changes/` for bug work.

## Principles of minimal fixes

- Make the smallest change that resolves the issue
- Do not refactor unrelated code
- Do not change formatting or style unless necessary
- Preserve existing behavior for all other cases
- If the fix feels large, reconsider whether you understand the root cause

## Before you start

1. Read the investigation findings from previous context
2. Understand the root cause clearly
3. Identify the exact files and lines that need modification

## Branch (mandatory)

Create or continue a **bugfix branch** — this branch will later be pushed and merged:

```bash
git checkout -b fix/{{ issue.identifier }}-brief-kebab-description
```

Use the format `fix/{{ issue.identifier }}-brief-kebab-description` (e.g. `fix/ENG-123-null-pointer-checkout`).

## Implementation steps

1. **Test first (when feasible):** add or adjust a test that fails before the fix and passes after (same spirit as TDD).

2. Apply the minimal code changes.

3. Run tests and the full hook suite the repo expects:

   ```bash
   uv run pytest tests/ -v -k "related_keyword"   # focused
   uv run pytest tests/ -v                        # broader changes
   uv run pre-commit run --all-files
   ```

4. **Commit locally** on the bugfix branch with clear messages.

## Do NOT (until merge-review prep)

- **`git push`** to open a remote branch for review
- **Open a PR/MR** — that happens in **`review-findings-route`** when the workflow routes `clean` or `needs_human` (after automated **code-review** passes)

Fixes and review iterations stay **local** until that routing step opens the PR for human **merge-review**.

## Completion criteria

Mark this stage complete when:

1. The fix is implemented on `fix/{{ issue.identifier }}-...`
2. **`uv run pre-commit run --all-files`** exits successfully
3. All relevant tests pass
4. Work is **committed locally** (not necessarily pushed)

Stokowski will advance to **`code-review`** next. Include `<stokowski:report>...</stokowski:report>` as required by the lifecycle prompt.

## Rework run

If you return here from **merge-review** (human requested changes after PR existed):

1. Read the feedback on Linear / in thread context.
2. Apply changes on the **same** bugfix branch; add commits (no force-push).
3. Re-run **`uv run pre-commit run --all-files`** and tests until green.
4. After you finish, the workflow will go through **code-review** and **review-findings-route** again — ensure the PR branch is updated when routing reaches merge-review prep.

## Do NOT

- Bundle unrelated fixes or features
- Leave debug prints or temporary logging in the final commit
- Push or open PR from this stage
