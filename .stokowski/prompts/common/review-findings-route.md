# Route after automated code review (agent-gate)

You have just **finished** the adversarial `code-review` pass (see prior context). Your job now is only to **classify the outcome** and emit the machine route — no new code review prose beyond what goes into `<stokowski:report>`.

**Routing source of truth:** Decide **`has_findings`** / **`clean`** using **only** the immediately prior **`code-review`** turn’s **`<stokowski:report>`**. A **P0–P3** item counts as **closed** only if that report lists it as **fixed** or **accepted with documented rationale** next to it. Text on Linear (or elsewhere) **without** the same in **`<stokowski:report>`** is **not** sufficient. If that report is missing, has no structured findings, or you cannot tell open vs accepted → **`needs_human`** (never guess **`clean`**).

**Transitions** — pick **exactly one** key for `"transition"` (same strings as below). Policy matches **`code-review`** / `prompts/feature/review.md`: **P0–P3** are merge blockers unless **explicitly accepted with documented rationale in that turn’s `<stokowski:report>`**; **P4** is never a merge blocker.

- **`has_findings`** — at least one **open P0, P1, P2, or P3** remains per the prior **`<stokowski:report>`** (not fixed and not accepted with rationale **there**). Send the issue to **`correct-findings-code-review`**, then it re-enters **`code-review`** after that agent completes.
- **`clean`** — the prior **`<stokowski:report>`** shows **no open P0–P3** (all resolved or accepted with rationale **in that report**). **P4-only** findings do **not** force `has_findings`. Proceed to human **`merge-review`** (after prep below).
- **`needs_human`** — ambiguous, conflicting, missing report, or you cannot decide safely; Stokowski also uses this as the **default** if routing JSON is missing or invalid → same as sending to **`merge-review`**.

## Merge-review prep (only for `clean` or `needs_human`)

If your chosen transition is **`clean`** or **`needs_human`**, the next step is the human **`merge-review`** gate. Maintainers need a **PR/MR** to review. Before you finish this turn, you MUST:

1. Ensure all intended work is **committed** on the work branch (`feature/<...>` or `fix/<...>`) with clear messages.
2. **Push with upstream if needed:** If **`origin/<branch>` does not exist yet** or the current branch has **no upstream** (`git push` would not know the remote), run **once**:
   ```bash
   git push -u origin <branch>
   ```
   (`--set-upstream` / `-u`.) Otherwise use `git push` as usual.
3. **Open** a PR/MR if none exists yet, and link the Linear issue in the description (e.g. `Fixes TEAM-123` or `Closes TEAM-123`):

   ```bash
   # GitHub
   gh pr create --title "..." --body "..."

   # GitLab
   glab mr create --title "..." --description "..."
   ```

4. If a PR/MR already exists for this branch, ensure the description still references the issue.

**Do not** perform the PR step when routing **`has_findings`** — fixes remain under review until a later pass may route to merge-review after P0–P3 are cleared or accepted.

## Required output (both parts)

1. **`<stokowski:report>...</stokowski:report>`** — short summary for Linear, following **`## ⚠️ REQUIRED: Structured Work Report`** in your assembled instructions (find that heading by exact title). State which transition you chose and, if relevant, how P0–P3 vs P4 drove it.
   You MUST include the mandatory **`## Commit Information`** block (four bullets: Branch, Commit SHA, Repository, MR URL) with real `git` values. **MR URL** here must match the fourth bullet (use `N/A — …` when no MR exists, as in those report rules; for `has_findings`, use an existing MR URL if any, otherwise `N/A — no PR/MR created in has_findings`).

2. **Routing block** — copy this shape **verbatim** (three lines: start marker, **one JSON line**, end marker). **Do not** put the markers back-to-back with nothing between them; **do not** omit the JSON line. Order vs. the report does not matter as long as both appear in your final message.

```
<<<STOKOWSKI_ROUTE>>>
{"transition": "clean"}
<<<END_STOKOWSKI_ROUTE>>>
```

Replace only `clean` with one of: `has_findings`, `clean`, `needs_human`.

**Other valid routing blocks (same pattern):**

```
<<<STOKOWSKI_ROUTE>>>
{"transition": "has_findings"}
<<<END_STOKOWSKI_ROUTE>>>
```

```
<<<STOKOWSKI_ROUTE>>>
{"transition": "needs_human"}
<<<END_STOKOWSKI_ROUTE>>>
```
