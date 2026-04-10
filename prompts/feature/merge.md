# Merge State

You are in the merge state. The PR/MR should already exist (it was opened when the workflow reached human **merge-review**, via `review-findings-route` when routing `clean` or `needs_human`). The PR has been approved and is ready to be merged into the main branch. Your task is to complete the merge process, clean up resources, and finalize the issue.

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

If checks are failing, **stop** and transition to `rework` state. Do not merge a broken PR.

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

3. Merge using squash strategy:
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

Move the Linear issue to the "Done" state. The orchestrator will automatically transition the issue when the merge is complete and the state machine reaches the terminal state.

Add a closing comment on Linear:
```
Merged via PR #<number>. Feature branch deleted. Issue complete.
```

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
- PR is merged into main
- Feature branch is deleted (local and remote)
- Linear issue is in "Done" state
- Closing comment is posted
- Workspace has no uncommitted changes

If any step fails, report the error and remain in this state. Do not proceed until merge is fully complete.

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
