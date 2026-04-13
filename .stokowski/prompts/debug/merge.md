# Merge State (debug workflow)

You are in the **debug** workflow **merge** state. The PR/MR should already exist (opened when the issue reached human **merge-review**, via `review-findings-route` when routing `clean` or `needs_human`). The PR has been approved and is ready to merge into the main branch.

**There is no OpenSpec step** in this workflow — bugfixes do not use `openspec/changes/`. Your job is to merge the **bugfix branch** and clean up.

## Execution order (mandatory)

1. **Pre-merge verification** (CI green, approved, no conflicts).
2. **Merge** the PR/MR (squash as below).
3. **Post-merge verification**, Linear comment, cleanup.

## Branch naming (reminder)

The fix should live on a branch like `fix/{{ issue.identifier }}-brief-kebab-description` — the same branch attached to the open PR. Do not merge unrelated branches.

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

**Always delete the bugfix branch** after merge (remote and local), per host defaults above.

## Pre-merge verification

Before merging, verify:

1. PR/MR status shows approved
2. All CI checks are passing
3. No merge conflicts
4. Branch is up to date with `main`

If checks are failing, **stop**. Do **not** merge. Post details on Linear. Have a human send the issue back toward the **`fix`** stage via the **merge-review** gate **rework** path (`rework_to` in `workflow.yaml`) — there is **no** agent transition named `rework` out of **merge**.

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

2. Pull latest from main if needed:
   ```bash
   git pull origin main
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
Merged via PR #<number>. Bugfix branch deleted. Issue complete.
```

**Issue state:** **Do not** move the Linear issue to **Done** yourself. When this **`merge`** state completes successfully, Stokowski moves the issue to the configured **terminal** state as part of transitioning to **`done`**.

## Cleanup

1. Delete local bugfix branch if still present:
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

- PR is merged into `main`
- Bugfix branch deleted (local and remote)
- Closing comment posted when possible
- Workspace has no uncommitted changes

## Rework run

If merge was attempted before but failed:

1. Identify the failure (CI, conflict, auth).
2. On conflict: rebase onto `main`, resolve, push, wait for CI, merge again.
3. On CI failure from the PR’s changes: post to Linear and stop (needs **merge-review** rework back to **`fix`**).
4. On flaky/infra CI: re-run and retry.

## Do NOT

- Run OpenSpec archive or create `openspec/` artifacts for this bugfix
- Make code changes beyond merge conflict resolution
- Open a second PR (push to the existing one)
- Skip CI or merge without approval
- Force-push the bugfix branch

Include `<stokowski:report>...</stokowski:report>` as required by the lifecycle prompt when you finish this turn.
