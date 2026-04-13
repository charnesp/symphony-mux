## Why

Today `tracker.project_slug` must be set explicitly in `workflow.yaml`. There is no fallback to an environment variable, unlike `tracker.api_key` which supports `LINEAR_API_KEY` as an env fallback via `resolved_api_key()`. Operators who manage multiple Stokowski deployments or rotate projects want to keep the slug out of the config file entirely — just like they already do with API keys via `.env`.

## What Changes

- Add a `resolved_project_slug()` method to `ServiceConfig` that mirrors the existing `resolved_api_key()` resolution pattern: literal value from YAML → `$VAR` reference resolved from env → `LINEAR_PROJECT_SLUG` env var as fallback.
- Replace all direct reads of `cfg.tracker.project_slug` throughout the codebase (orchestrator, main, config validation, dry run) with `cfg.resolved_project_slug()`.
- Update `validate_config()` to call `resolved_project_slug()` so the env fallback is checked before reporting "Missing tracker.project_slug".
- Update `agent_env()` to use the resolved value.
- Update documentation (README, workflow.example.yaml comments, CLAUDE.md) to mention the `LINEAR_PROJECT_SLUG` env var option.

## Capabilities

### Modified Capabilities

- `workflow-config`: `ServiceConfig` gains `resolved_project_slug()` with the same three-tier priority as `resolved_api_key()`: literal → `$VAR` → env fallback.

## Impact

- `stokowski/config.py` — new `resolved_project_slug()` method; `validate_config()` and `agent_env()` updated.
- `stokowski/orchestrator.py` — all `self.cfg.tracker.project_slug` references replaced with `self.cfg.resolved_project_slug()`.
- `stokowski/main.py` — dry-run display and fetch calls updated.
- `workflow.example.yaml` — comment noting `LINEAR_PROJECT_SLUG` as alternative.
- `README.md` — troubleshooting table and config reference updated.
- `CLAUDE.md` — `resolved_api_key` section updated to include `resolved_project_slug`.
- Tests for the new resolution method and updated validation.
