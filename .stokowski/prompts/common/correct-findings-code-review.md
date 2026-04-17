# Correct findings from code review

You are fixing issues identified in the last **`code-review`** run. Address the findings in the report / thread context; keep changes minimal and well-tested.

When done, the workflow returns to **`code-review`** for another automated review pass.

## What to do

1. Read the review findings in Linear (and in your `<stokowski:report>` / issue thread context).
2. Address each point on the existing local work branch (`feature/<...>` or `fix/<...>`).
3. Run `npm audit`, `npm run test`, and `npm run lint`, then fix until all checks pass (same bar as implementation/fix).
4. Add commits as needed, then push to `origin` (do not force-push). **If the remote branch does not exist yet or your branch has no upstream**, run once:
   ```bash
   git push -u origin <branch>
   ```
   (`-u` / `--set-upstream`.) Otherwise `git push` is enough.

**Do not** open a PR/MR from this stage — PR/MR creation still happens only when **`review-findings-route`** selects `clean` or `needs_human` (merge-review prep).

**Do not** skip or bypass quality checks (`git commit --no-verify`, or stopping before all of `npm audit`, `npm run test`, and `npm run lint` are green).

Include a full `<stokowski:report>` as usual when you finish this turn.

The mandatory **`## Commit Information`** section (four bullets: Branch, Commit SHA, Repository, MR URL) MUST be present and filled from `git` after your commits — per **`## ⚠️ REQUIRED: Structured Work Report`** in your assembled instructions (find that heading). Do not rely on `## Technical Details` alone for branch or SHA.
