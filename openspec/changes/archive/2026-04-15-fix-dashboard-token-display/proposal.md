## Why

The web dashboard incorrectly displays 0 tokens and turn 1 for issues that have actually consumed significant tokens (e.g., 1.9M) across multiple runs (e.g., run 2). This makes it impossible for operators to monitor actual token usage and track progress accurately.

## What Changes

- Fix token accumulation in `RunAttempt` to aggregate across multiple turns within a run, not just the current turn
- Add per-issue token tracking that persists across state transitions
- Update web dashboard to display cumulative tokens for issues at gates (currently hardcoded to 0)
- Ensure `turn_count` in dashboard reflects the actual run number from `_issue_state_runs`, not just the current turn counter

## Capabilities

### New Capabilities
- `dashboard-token-tracking`: Per-issue cumulative token and turn tracking for accurate dashboard display

### Modified Capabilities
- *(none - this is a bugfix that doesn't change spec-level behavior)*

## Impact

- `stokowski/orchestrator.py`: Add per-issue token accumulation tracking
- `stokowski/models.py`: Consider adding cumulative token fields to track totals across turns
- `stokowski/runner.py`: Token extraction logic remains unchanged, but accumulation logic needs review
- `stokowski/web.py`: Dashboard JavaScript to use cumulative token data for gates
- Dashboard display accuracy for operators monitoring active agents
