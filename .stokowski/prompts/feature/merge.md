# Merge State

You are in the merge state. The PR/MR should already exist (it was opened when the workflow reached human **merge-review**, via `review-findings-route` when routing `clean` or `needs_human`). The PR has been approved and is ready to be merged into the main branch. Your task is to complete the merge process, clean up resources, and finalize the issue.

## Execution order (mandatory)

1. **Pre-merge verification** (CI green, approved, no conflicts).
2. **OpenSpec archive** — **`/openspec-archive-change`** **before** any `gh pr merge` / `glab mr merge`, so the archive lands on the feature branch and is included in the same PR.
3. **Merge** the PR/MR (squash as configured below).
4. **Post-merge verification**, Linear comment, cleanup.

If `gh`/`glab` cannot merge (auth, etc.), you must still have **completed archiving and pushed** the branch first, so a human merge on the web already includes the archived OpenSpec change.

## Merge Requirements

Use **squash merge** for a clean history.

**GitHub (gh):**
```bash
gh pr merge --squash --delete-branch
```

**GitLab (glab):**
```bash
glab mr merge --squash
```

Or if squash is disabled, use rebase:
```bash
# GitHub
gh pr merge --rebase --delete-branch

# GitLab
glab mr merge --rebase
```

**Always delete the feature branch** after merge. Do not skip this step.

## Pre-Merge Verification

Before merging, verify:
1. PR/MR status shows "Approved"
2. All CI checks are passing (green)
3. No merge conflicts exist
4. Branch is up to date with main

If checks are failing, **stop**. Do **not** merge. Post details on Linear. Have a human send the issue back toward **implementation** via the **merge-review** gate **rework** path (`rework_to` in your `workflow.yaml`, e.g. `implement`) — there is **no** agent transition named `rework` out of **merge** in the example feature workflow.

## OpenSpec (required — before merge)

**Run this only after pre-merge verification passes.** Do **not** wait for the PR to be merged.

Follow the **`openspec-archive-change`** skill (**`/openspec-archive-change`**). Do not re-document those steps here — the skill handles selection, completion checks, optional delta sync, and moving `openspec/changes/<name>/` to `openspec/changes/archive/`.

**Then ensure the branch is up to date on the remote** before merging: if archiving created or modified files, **commit** (if not already done by the skill flow) and **`git push`** so the open PR includes the archive.

**Skip archiving** only when **no** `openspec/changes/<name>/` directory applies to this issue’s work (confirm under `openspec/changes/`). In **`<stokowski:report>`**, state explicitly: e.g. `Skipped /openspec-archive-change: no openspec change directory for this issue` (or name the change if scope was non-OpenSpec). Do **not** skip because archiving is inconvenient.

## Merge Steps

1. Find and checkout the PR/MR:
   ```bash
   # GitHub
   gh pr list --head <branch-name>
   gh pr checkout <number>

   # GitLab
   glab mr list --source-branch <branch-name>
   glab mr checkout <number>
   ```

2. Pull latest changes from main:
   ```bash
   git pull origin main
   ```

3. Merge using squash strategy (**only after** OpenSpec archiving is done and pushed when applicable):
   ```bash
   # GitHub
   gh pr merge <number> --squash --delete-branch

   # GitLab
   glab mr merge <number> --squash
   ```

4. Delete the remote branch (GitLab doesn't auto-delete):
   ```bash
   # GitLab only
   git push origin --delete <branch-name>
   ```

## Post-Merge Verification

After merging, verify success:

**GitHub:**
```bash
gh pr view <number> --json state,merged
```

**GitLab:**
```bash
glab mr view <number>
```

Confirm:
- State shows "MERGED" (GitHub) or "Merged" (GitLab)
- Branch is deleted

## Linear Issue Update

Post a closing comment on Linear (optional but recommended if you can):
```
Merged via PR #<number>. Feature branch deleted. Issue complete.
```

**Issue state:** **Do not** move the Linear issue to **Done** yourself. When this **`merge`** state completes successfully, Stokowski’s **orchestrator** moves the issue to your configured **terminal** Linear state (first entry under `linear_states.terminal` in `workflow.yaml`, e.g. Done) as part of transitioning to the workflow’s **`done`** state. You only post the human-facing comment above (if your tools allow).

## Cleanup

1. Delete the local feature branch if still present:
   ```bash
   git branch -d <branch-name>
   ```

2. Prune remote tracking branches:
   ```bash
   git fetch --prune
   ```

3. Verify workspace is clean (`git status` shows no uncommitted changes)

## Completion Criteria

Mark this state complete when:
- **`/openspec-archive-change`** has been applied for the active change (or explicitly skipped with reason if none), **before** merge, with any resulting commits **pushed** to the PR branch when applicable
- PR is merged into main
- Feature branch is deleted (local and remote)
- Closing comment is posted when your tools allow (Linear **state** → terminal is done by Stokowski, not you)
- Workspace has no uncommitted changes

If any step fails, report the error and remain in this state. Do not proceed until archiving (when required) and merge are fully complete.

## Rework run

If this is a rework run (merge was attempted before but failed):

1. Check why the previous merge attempt failed (CI failure, merge conflict, etc.).
2. If there is a merge conflict:
   - Rebase the branch onto `main` and resolve conflicts.
   - Push the updated branch.
   - Wait for CI to pass, then merge.
3. If CI failed:
   - Read the failure logs.
   - If it is a test failure caused by the PR's changes, post details to Linear and stop (this needs to go back to implementation).
   - If it is a flaky or infrastructure issue, re-run and retry the merge.
4. Update the Linear tracking comment with what happened.

## Do NOT

- Make code changes beyond conflict resolution
- Open new PRs (push to the existing one)
- Skip CI checks
- Merge without approval
- Force-push to the feature branch
