# Merge State

You are in the merge state. The PR/MR should already exist (opened when the workflow reached human **merge-review**, via `review-findings-route` when routing `clean` or `needs_human`). The PR has been approved and is ready to be merged into the `master` branch.

This prompt is shared by **debug** and **feature** workflows. The branch can be either `fix/<...>` or `feature/<...>` depending on the workflow.

## Execution order (mandatory)

1. **Pre-merge verification** (CI green, approved, no conflicts).
2. **OpenSpec archive (conditional)** — if this issue has an applicable `openspec/changes/<name>/` directory, run **`/openspec-archive-change`** before merge; otherwise explicitly skip with reason.
3. **Merge** the PR/MR (squash as below).
4. **Post-merge verification**, Linear comment, cleanup.

## Merge requirements

Use **squash merge** for a clean history.

**GitHub (`gh`):**
```bash
gh pr merge --squash --delete-branch
```

**GitLab (`glab`):**
```bash
glab mr merge --squash
```

If squash is disabled, use rebase:
```bash
# GitHub
gh pr merge --rebase --delete-branch

# GitLab
glab mr merge --rebase
```

Always delete the work branch after merge (remote and local), per host defaults above.

## Pre-merge verification

Before merging, verify:
1. PR/MR status shows approved
2. All CI checks are passing
3. No merge conflicts
4. Branch is up to date with `master`

If checks are failing, **stop**. Do **not** merge. Post details on Linear. Have a human send the issue back through the **merge-review** gate rework path (`rework_to` in `workflow.yaml`, e.g. `fix` or `implement`) — there is no direct agent transition named `rework` out of **merge**.

## OpenSpec archive (conditional)

If this issue has an applicable `openspec/changes/<name>/` directory:
1. Run **`/openspec-archive-change`**.
2. Ensure any resulting archive changes are committed and pushed before merge.

If there is no applicable OpenSpec change directory for this issue, skip this step and state it explicitly in `<stokowski:report>`.

Do not use branch naming (`fix/...` vs `feature/...`) as the decision rule. Decide only from issue/workflow context and whether an applicable OpenSpec change directory exists.

## Merge steps

1. Find and check out the PR/MR:
   ```bash
   # GitHub
   gh pr list --head <branch-name>
   gh pr checkout <number>

   # GitLab
   glab mr list --source-branch <branch-name>
   glab mr checkout <number>
   ```

2. Pull latest from `master` if needed:
   ```bash
   git pull origin master
   ```

3. Merge:
   ```bash
   # GitHub
   gh pr merge <number> --squash --delete-branch

   # GitLab
   glab mr merge <number> --squash
   ```

4. **GitLab only** — delete remote branch if not auto-deleted:
   ```bash
   git push origin --delete <branch-name>
   ```

## Post-merge verification

**GitHub:**
```bash
gh pr view <number> --json state,merged
```

**GitLab:**
```bash
glab mr view <number>
```

Confirm state is merged and the branch is gone.

## Linear issue update

Optional closing comment:
```
Merged via PR/MR #<number>. Work branch deleted. Issue complete.
```

Issue state: **Do not** move the Linear issue to **Done** yourself. When this **`merge`** state completes successfully, Stokowski transitions the issue to the configured terminal state.

## Cleanup

1. Delete local branch if still present:
   ```bash
   git branch -d <branch-name>
   ```

2. Prune remotes:
   ```bash
   git fetch --prune
   ```

3. `git status` clean

## Completion criteria

Mark complete when:
- PR/MR is merged into `master`
- Work branch deleted (local and remote)
- If OpenSpec archive applied, resulting changes are included and pushed before merge
- Closing comment posted when possible
- Workspace has no uncommitted changes

## Git validation for `<stokowski:report>` (mandatory)

Your report must be **grounded in real git and host state**, not a narrative summary. Under **`## Technical Details`**, add a subsection **`### Git validation (raw)`** and paste **verbatim** terminal output (no paraphrase) for:

```text
$ git checkout master && git pull origin master

$ git log -1 --oneline

$ git branch -vv
```

(If you are not on `master` when capturing `git branch -vv`, show **`git branch -vv`** after `git checkout master` so `master`’s tracking and tip are visible.)

**MR URL (`## Commit Information`, fourth bullet):**

- If the merge was done **via GitLab or GitHub** (normal path: `glab mr merge` / `gh pr merge`), **`MR URL` is mandatory** — use the canonical web URL of the merged MR/PR (not `N/A`).
- Use **`N/A`** **only** in **rare** cases (e.g. merge performed outside the normal MR flow and you have no MR object). If you use `N/A`, add **one explicit sentence** in **`### Git validation (raw)`** explaining why (no vague “merged directly” without justification).

**`Commit SHA` in `## Commit Information`:** must match the **current `master` HEAD** after merge — i.e. the same commit as `git log -1` on `master` in the block above (full SHA in the report, one-line log for human scan).

## Rework run

If merge was attempted before but failed:
1. Identify the failure (CI, conflict, auth).
2. On conflict: rebase onto `master`, resolve, push, wait for CI, merge again.
3. On CI failure caused by PR changes: post to Linear and stop (needs merge-review rework to the configured implementation state).
4. On flaky/infra CI: re-run and retry.

## Do NOT

- Make code changes beyond merge conflict resolution
- Open a second PR/MR (push to the existing one)
- Skip CI or merge without approval
- Force-push the work branch

When you finish, include `<stokowski:report>...</stokowski:report>` following the rules under the heading **`## ⚠️ REQUIRED: Structured Work Report`** in your **full instructions for this turn**. Search the assembled prompt for that exact heading — it may appear **before or after** this merge-stage text; order does not matter. Those rules (including mandatory **`## Commit Information`**) are authoritative. For **`## Commit Information`** in this stage: **`Branch`** is typically `master` (with optional tree URL); **`Commit SHA`** is `master`’s tip after merge (must align with **`### Git validation (raw)`**); **`MR URL`** must be the merged MR/PR URL when merge went through GitLab/GitHub — see **Git validation for `<stokowski:report>`** above.
