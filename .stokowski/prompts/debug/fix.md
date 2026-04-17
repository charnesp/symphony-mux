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

Create or continue a **bugfix branch**, and ensure it exists on `origin`:

```bash
git checkout -b fix/{{ issue.identifier }}-brief-kebab-description
```

Use the format `fix/{{ issue.identifier }}-brief-kebab-description` (e.g. `fix/ENG-123-null-pointer-checkout`).

After creating or switching to the branch, ensure it exists on **`origin`** with **upstream** set:

- If **`origin/<branch>` does not exist yet** (first publish) or your local branch has **no upstream** (nothing tracked under `origin/`), run **once**:
  ```bash
  git push -u origin <branch>
  ```
  (`-u` is `--set-upstream`: creates the remote branch if needed and links your local branch to it.)
- If the remote branch already exists **and** upstream is already configured, you do not need `-u` again for routine pushes.

## Implementation steps

1. **Test first (when feasible):** add or adjust a test that fails before the fix and passes after (same spirit as TDD).

2. Apply the minimal code changes.

3. Run tests and the full local quality checks the repo expects:

   ```bash
   npm run test
   npm audit
   npm run lint
   ```

4. **Commit and push** on the bugfix branch with clear messages:

   ```bash
   git commit -m "fix: ..."
   git push
   ```

   If `git push` fails because **no upstream is configured**, run `git push -u origin <branch>` once, then use `git push` for later commits.

## Do NOT (until merge-review prep)

- **Open a PR/MR** — that happens in **`review-findings-route`** when the workflow routes `clean` or `needs_human` (after automated **code-review** passes)
- Work on a second bugfix branch for the same issue

## Completion criteria

Mark this stage complete when:

1. The fix is implemented on `fix/{{ issue.identifier }}-...`
2. `npm audit`, `npm run test`, and `npm run lint` all pass
3. All relevant tests pass
4. Work is **committed and pushed** to `origin` on the bugfix branch
5. The `<stokowski:report>` includes the mandatory **`## Commit Information`** block (four bullets: Branch, Commit SHA, Repository, MR URL) filled from `git` — per **`## ⚠️ REQUIRED: Structured Work Report`** in your assembled instructions (find that heading; it may appear before or after this text).

Stokowski will advance to **`code-review`** next. Include `<stokowski:report>...</stokowski:report>` per that same section. Example for **`## Commit Information`**:

```markdown
## Commit Information

* **Branch:** `fix/{{ issue.identifier }}-brief-kebab-description` — `https://gitlab.com/<group>/<project>/-/tree/<branch>`
* **Commit SHA:** `<output of git rev-parse HEAD>`
* **Repository:** `<git remote get-url origin or group/project>`
* **MR URL:** `N/A — MR not created until merge-review prep` (unless an MR already exists)
```

## Rework run

If you return here from **merge-review** (human requested changes after PR existed):

1. Read the feedback on Linear / in thread context.
2. Apply changes on the **same** bugfix branch; add commits and push (no force-push). Use `git push -u origin <branch>` if upstream is not set; otherwise `git push`.
3. Re-run `npm audit`, `npm run test`, and `npm run lint` until green.
4. After you finish, the workflow will go through **code-review** and **review-findings-route** again — keep the remote branch updated.

## Do NOT

- Bundle unrelated fixes or features
- Leave debug prints or temporary logging in the final commit
- Open PR from this stage
