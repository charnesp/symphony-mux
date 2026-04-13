## Context

`resolved_api_key()` already implements a three-tier resolution pattern for the API key: (1) literal value from YAML, (2) `$VAR` reference resolved from env, (3) `LINEAR_API_KEY` env var as fallback. `project_slug` currently only supports tiers 1 and 2 (via `_resolve_env`), but has no env-var fallback when omitted entirely from the YAML.

## Goals / Non-Goals

**Goals:**

- Add `resolved_project_slug()` to `ServiceConfig` with identical three-tier priority to `resolved_api_key()`:
  1. Literal value from YAML (e.g. `project_slug: "abc123"`)
  2. `$VAR` reference resolved from env (e.g. `project_slug: "$MY_SLUG"`)
  3. `LINEAR_PROJECT_SLUG` env var as fallback when the YAML value is empty
- If `project_slug` is set in `workflow.yaml` (literal or `$VAR`), it takes precedence over the env var — matching the issue requirement.
- Update all consumers to use the resolved value.
- Update validation so it doesn't falsely report "Missing tracker.project_slug" when `LINEAR_PROJECT_SLUG` is set.

**Non-Goals:**

- Changing the behavior of `_resolve_env()` or `resolved_api_key()`.
- Adding env var fallbacks for other tracker fields (e.g. `endpoint`) beyond what `agent_env()` already handles.
- Supporting `project_slug` as a CLI flag (out of scope).

## Decisions

### 1. Resolution method name and location

**Choice:** `resolved_project_slug()` on `ServiceConfig`, next to `resolved_api_key()`.

**Why:** Follows the established pattern exactly. No new module, no new abstraction — just a sibling method with the same shape.

### 2. Priority order

**Choice:**

1. `self.tracker.project_slug` — if non-empty, resolve `$VAR` references via `_resolve_env()` and return.
2. `os.environ.get("LINEAR_PROJECT_SLUG", "")` — env var fallback.

**Why:** This matches both `resolved_api_key()` and the issue requirement ("If the project_slug is setup in the workflow.yaml, it will still be used instead of the env variable data").

### 3. Validation update

**Choice:** In `validate_config()`, replace `if not cfg.tracker.project_slug:` with `if not cfg.resolved_project_slug():`. Update the error message to mention `LINEAR_PROJECT_SLUG`.

**Why:** Prevents false-positive validation errors when the slug is provided via env var only.

### 4. Consumers to update

**Choice:** Replace all `cfg.tracker.project_slug` / `self.cfg.tracker.project_slug` with the resolved variant:

- `orchestrator.py` lines 137, 196, 727, 821, 954, 1730
- `main.py` lines 450, 479
- `config.py` `agent_env()` (already resolves, but should use the method for consistency)

**Why:** Ensures every code path uses the same resolved value. Direct reads of the raw field would miss the env fallback.

### 5. agent_env() consistency

**Choice:** `agent_env()` already calls `_resolve_env(self.tracker.project_slug)`. Update it to use `resolved_project_slug()` instead, so the env fallback is also passed to agent subprocesses.

**Why:** Currently if the YAML is empty and `LINEAR_PROJECT_SLUG` is set, `agent_env()` would set `LINEAR_PROJECT_SLUG=""` instead of the actual value.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Breaking change if code reads `tracker.project_slug` directly | Grep for all usages and replace systematically |
| Env var name collision | `LINEAR_PROJECT_SLUG` is already used by `agent_env()` — no new name introduced |
| `project_slug` set to empty string in YAML (vs absent) | Empty string is falsy, so env fallback activates — consistent with `resolved_api_key()` |

## Migration Plan

- Non-breaking: existing configs with `project_slug` in YAML continue working identically.
- Operators can now omit `project_slug` from YAML and set `LINEAR_PROJECT_SLUG` in `.env` instead.
