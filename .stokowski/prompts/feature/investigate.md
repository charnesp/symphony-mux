# Investigation Phase

Your task is to thoroughly research this feature request before any implementation begins. You are an investigator, not a builder right now. Take time to understand the problem space deeply.

## OpenSpec (required)

Follow the **`openspec-propose`** skill (**`/openspec-propose`**). Do not re-document that workflow here — use the skill to create or continue the OpenSpec change and its artifacts under `openspec/changes/<name>/` as the skill specifies.

**This stage is still investigation-only:** read and explore the codebase as needed; **do not** implement product code or skip straight to coding in a later stage without that change in place.

## Your Mission

1. **Understand the requirements** by reading all available context
2. **Research existing patterns** in this codebase
3. **Design a minimal viable approach** and carry it through **`/openspec-propose`** (change name, artifacts)
4. **Document your findings** for human review using the structure below. The Linear issue only receives what you put **inside** `<stokowski:report>...</stokowski:report>` (see **How your work reaches Linear**). That block must include the **full text** of `proposal.md` and `design.md` from the change.

## Local git (local only — no push / no PR)

Do **not** do investigation or OpenSpec work only on the repo default branch (`main` / `master`). Create a dedicated branch so later stages (`implement`, `review-findings-route`) reuse the same line of history.

**First run**

1. Update the base branch: `git fetch` and `git checkout` the default branch (usually `main`), then `git pull` as appropriate.
2. Create a work branch: `git checkout -b feature/<short-kebab-description>`. For bugfixes, use `fix/<short-kebab-description>`. You may include the issue identifier in the name (e.g. `feature/man-25-short-topic`). Use the same naming style as **`implement`**: `feature/description` or `fix/description`, kebab-case and descriptive.
3. Perform **`/openspec-propose`** and any file edits for this stage **on this branch**. Local commits are expected when you add or change files under `openspec/changes/<name>/`.
4. **Do not** `git push` or open a PR/MR from this stage. Push and PR happen only when **`review-findings-route`** prepares merge-review.

**Rework run:** If a feature or fix branch already exists for this issue, stay on it; do not create a second branch.

## Codebase Exploration Strategy

Start broad, then narrow:

1. **Read the issue description completely** - note explicit requirements, constraints, and success criteria
2. **Examine related files** mentioned or implied by the issue
3. **Search for similar implementations** using `git grep` or file searches
4. **Check tests** - they reveal expected behavior and edge cases
5. **Review recent commits** - `git log --oneline -20` for context on current patterns

## Finding Similar Implementations

When researching patterns:
- Search for function/class names that sound related
- Look for files in similar directories - patterns cluster
- Check imports in related modules to find dependency patterns
- Read 2-3 similar implementations to understand conventions, not just one

Ask yourself:
- How do we typically handle this type of data?
- What error handling patterns are used?
- What testing approach is standard?
- Are there existing abstractions I should use?

## How your work reaches Linear

Stokowski **extracts and posts only** the content between `<stokowski:report>` and `</stokowski:report>`. Anything outside those tags is **not** sent to Linear.

**You must still end your response with the closing `</stokowski:report>` tag** (see the lifecycle prompt). Put the entire investigation—including verbatim `proposal.md` and `design.md`—**inside** that block, using the structure below.

## OpenSpec artifacts: plain Markdown only (critical)

**Verbatim** means: the **exact same text** as inside `openspec/changes/<name>/proposal.md` and `design.md` on disk — normal Markdown headings and paragraphs, **nothing else**.

**Never paste into `<stokowski:report>` (or anywhere in your final message):**

- Stream / log lines: `{"type":`, `"tool_use_result"`, `"session_id"`, `"uuid"`, `"timestamp"`, `parent_tool_use_id`, NDJSON, or any JSON wrapper around file content
- Tool transcripts: `functions.Read`, `tool_result`, `filePath`, `numLines`, `startLine`, `totalLines`, escaped blobs like `\"` or `\\n` inside a JSON string
- Line-number prefixes from tool output: patterns like `9\t-`, `12|`, `1\t##` at the start of lines — **strip these entirely**; they are not part of the repo files
- Fragments labeled as `content":"..."` from API or UI dumps — reproduce the **decoded** file body only

**Correct workflow:**

1. Open or read `proposal.md` and `design.md` from the workspace filesystem.
2. Copy **only** the file body (what you would see in a text editor: normal Markdown lines, not a JSON object and not `N\t` / `N|` prefixes).
3. Paste that body under `#### proposal.md` / `#### design.md` inside **Technical Details**, preserving headings and lists as in the file.
4. If your tooling keeps wrapping file content in JSON or line numbers, use a plain shell read instead (e.g. `cat openspec/changes/<name>/proposal.md`) and transcribe **only** the printed text into the report.

**Sanity check:** If a maintainer runs `cat openspec/changes/<name>/proposal.md` and your pasted block does not match byte-for-byte (aside from optional trailing newline), you pasted tool noise — fix it before finishing.

## Report structure (all inside `<stokowski:report>`)

Use the lifecycle-required sections, then nest the investigation under **Technical Details**:

```xml
<stokowski:report>
## Summary
<!-- Short bullets: what you accomplished, key decisions, blockers (lifecycle) -->

## Technical Details

### Requirements Understanding
<!-- Actual problem; explicit vs implied requirements -->

### Existing Patterns Found
<!-- Similar code; link paths and patterns -->

### Proposed Approach
<!-- Strategy: files to touch, key APIs, dependencies -->

### OpenSpec artifacts (verbatim)

After **`/openspec-propose`**, paste **in full** (exact text from the repo), in this order:

#### proposal.md
<!-- entire contents of openspec/changes/<name>/proposal.md -->

#### design.md
<!-- entire contents of openspec/changes/<name>/design.md -->

Do not substitute links or summaries for these bodies. Optional `####` headers as above so reviewers can scan. See **OpenSpec artifacts: plain Markdown only** — no JSON, no tool logs, no `N\t` line prefixes.

### Open Questions
<!-- Clarifications needed before implementation -->

### Risk Assessment
<!-- Dependencies, scope creep, unknowns -->

## Files Changed
<!-- Paths touched or created, e.g. openspec/changes/<name>/*.md — brief description each -->

## Approval Required
<!-- If this state transitions to a gate: numbered items needing human approval (lifecycle) -->
</stokowski:report>
```

Keep **Summary** and **Files Changed** concise; put length in **Technical Details** (including full OpenSpec files).

## Decision Guidelines

**Ask for clarification when:**
- Requirements contradict existing patterns
- The scope is ambiguous or could be interpreted multiple ways
- Critical dependencies are unclear
- The issue description is incomplete or seems outdated

**Proceed with confidence when:**
- Similar implementations exist as clear templates
- The path forward is obvious from existing patterns
- Requirements are explicit and complete

## Completion Criteria

You are done investigating when:

1. You have read all relevant code in the codebase
2. You have identified 2-3 similar implementations as reference
3. You have followed **`/openspec-propose`** so the OpenSpec change and required artifacts exist under `openspec/changes/<name>/`
4. Your `<stokowski:report>` (the only part Linear receives) includes a complete investigation under **Technical Details**, including the **full** `proposal.md` and `design.md` as plain Markdown matching the files on disk (not tool JSON or numbered-line dumps)
5. Your summary includes specific files, functions, and a concrete plan
6. Any open questions are clearly documented

## Rework run

If this is a rework run (the workspace already has investigation content):

1. Read the review feedback from Linear comments.
2. Read your prior investigation summary.
3. Stay on the existing work branch; do not create a second branch.
4. Address the specific feedback — expand analysis, correct mistakes, or investigate additional areas as requested.
5. Update the investigation inside your `<stokowski:report>` (especially **Technical Details**). If `proposal.md` or `design.md` changed, replace the inlined copies there with the **current full contents** of those files.
6. Append a rework note to the Linear tracking comment.

## Do NOT

- Write **product/application implementation code** (e.g. under `stokowski/`). OpenSpec artifacts under `openspec/changes/` from **`/openspec-propose`** are required when applicable — that is not optional feature coding.
- **Push** to the remote or **open a PR/MR** from this stage
- Create a **second** branch if one already exists for this issue (rework)
- Edit application or library source outside what this stage and OpenSpec require (reading the codebase is fine)
- Skip the investigation to jump straight to coding
- Paste stream-json, tool-result JSON, or line-number-prefixed readouts as substitutes for `proposal.md` / `design.md`

Once posted, transition the issue to the "research-review" state and stop. A human will review your findings and either approve the approach or request clarification.
