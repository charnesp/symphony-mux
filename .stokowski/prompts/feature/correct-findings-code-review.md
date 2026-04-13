# Correct findings from code review

You are fixing issues identified in the last **`code-review`** run. Address the findings in the report / thread context; keep changes minimal and well-tested.

When done, the workflow returns to **`code-review`** for another automated review pass.

## What to do

1. Read the review findings in Linear (and in your `<stokowski:report>` / issue thread context).
2. Address each point on the existing local branch.
3. Run **`uv run pre-commit run --all-files`** and fix until all hooks pass (same bar as **implement** — not pytest/ruff alone).
4. Add normal local commits as needed (do not force-push).

**Do not** push to origin or open a PR/MR from this stage — that happens only when **`review-findings-route`** selects `clean` or `needs_human` (merge-review prep).

**Do not** skip or bypass pre-commit (`SKIP=…`, `git commit --no-verify`, or stopping after individual tools instead of **`uv run pre-commit run --all-files`**).

Include a full `<stokowski:report>` as usual when you finish this turn.
