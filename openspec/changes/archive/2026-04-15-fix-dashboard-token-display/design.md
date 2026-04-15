## Context

The web dashboard displays per-issue token usage and turn counts. Currently, it shows:
- **0 tokens** and **turn 1** for an issue that has actually consumed 1.9M tokens on run 2

### Root Cause Analysis

After investigating the codebase, I found two separate issues:

**Issue 1: Token accumulation only happens per-turn, not per-run**
In `stokowski/runner.py`, the `_process_event` function extracts tokens from the `result` event:
```python
if event_type == "result":
    usage = event.get("usage", {})
    if usage:
        attempt.input_tokens = usage.get("input_tokens", attempt.input_tokens)
        attempt.output_tokens = usage.get("output_tokens", attempt.output_tokens)
        attempt.total_tokens = usage.get("total_tokens", 0) or attempt.input_tokens + attempt.output_tokens
```

The problem: These are **set**, not **accumulated**. Each turn overwrites the previous values instead of adding to them.

**Issue 2: Running attempts are removed from dashboard view**
In `stokowski/orchestrator.py`, `_on_worker_exit`:
1. Adds the attempt's tokens to global totals (lines 1623-1625)
2. Pops the attempt from `self.running` (line 1689)

The `get_state_snapshot` method only iterates over `self.running.values()` for the "running" section. Once a turn completes, the issue disappears from the running list until it starts again.

**Issue 3: Gates show hardcoded 0 tokens**
In `stokowski/web.py`, lines 597-605, gates are mapped with:
```javascript
tokens: { total_tokens: 0 },
```

This is hardcoded to 0, so issues waiting at gates never show their actual token usage.

**Issue 4: `turn_count` vs `run` number mismatch**
The `turn_count` field in `RunAttempt` counts turns within the current execution, but the dashboard should display the run number (from `_issue_state_runs`).

## Goals / Non-Goals

**Goals:**
- Accurately display cumulative token usage per issue in the dashboard
- Show correct run numbers for issues at gates
- Maintain backward compatibility with existing tracking
- Minimal changes to core orchestration logic

**Non-Goals:**
- Changing the stream-json parsing logic (working correctly)
- Modifying how tokens are extracted from Claude Code output
- Adding persistent database storage
- Changing the Linear tracking comment format

## Decisions

### Decision 1: Add per-issue cumulative token tracking in Orchestrator

**Approach:** Add a dictionary `_issue_tokens` to the Orchestrator that maps `issue_id` to cumulative token totals.

**Rationale:**
- Tokens are already accumulated to global totals in `_on_worker_exit`
- Same pattern can be extended to track per-issue totals
- Simple, minimal change to existing code
- Survives across turns for the same issue

**Alternative considered:** Accumulate in `RunAttempt` - rejected because `RunAttempt` is recreated fresh for each dispatch.

### Decision 2: Include cumulative tokens in `get_state_snapshot`

**Approach:** Add a new section to the state snapshot that includes cumulative token data for all recently active issues, not just currently running ones.

**Rationale:**
- Dashboard needs token data for issues at gates (which aren't running)
- Issues between turns should still show their cumulative usage
- Minimal changes to the dashboard JavaScript

### Decision 3: Fix gate token display in dashboard JavaScript

**Approach:** Update the gate mapping in `renderAgents` to use actual token data instead of hardcoded 0.

**Rationale:**
- Simplest fix for the immediate bug
- Requires Decision 2 (cumulative token data) to be meaningful

## Risks / Trade-offs

**Risk:** Memory growth from per-issue token tracking
- **Mitigation:** Only track for issues that are currently active or recently completed (within 1 month). Implement cleanup when issues reach terminal states or exceed the age limit.

**Risk:** Token data lost on orchestrator restart
- **Mitigation:** Confirmed acceptable - tokens are for monitoring only. Per design decision, tracking resets on restart and only includes issues active in the last month.

**Risk:** Dashboard shows stale data if issue hasn't run recently
- **Mitigation:** Per design decision, token data for issues older than 1 month is excluded.

## Memory Management Requirements

Based on design decisions, the implementation must:
- **Reset on restart:** `_issue_tokens` dictionary starts fresh on orchestrator restart
- **1-month age limit:** Do not include token data for issues older than 1 month (based on issue `created_at` or last activity)
- **Cleanup on terminal state:** Remove entries when issues reach terminal states

## Migration Plan

1. **Phase 1:** Add `_issue_tokens` tracking to Orchestrator
   - Initialize in `__init__`
   - Update in `_on_worker_exit`
   - Clear when issues reach terminal states
   - Implement 1-month age filtering in `get_state_snapshot`

2. **Phase 2:** Update `get_state_snapshot` to include cumulative tokens
   - Add per-issue token data to the snapshot
   - Include for both running and gate-waiting issues
   - Filter out issues older than 1 month

3. **Phase 3:** Update dashboard JavaScript
   - Use cumulative tokens for gates instead of hardcoded 0
   - Display correct run numbers

4. **Phase 4:** Testing
   - Verify token accumulation across multiple turns
   - Verify gate display shows correct data
   - Verify cleanup on terminal state
   - Verify age filtering excludes old issues

## Open Questions (Resolved)

1. **Should we persist cumulative tokens to Linear comments for crash recovery?** → No need. Token tracking is in-memory only and resets on restart.
2. **Should the global totals metric in the dashboard show cumulative totals or just current session?** → Show all tokens consumed since Stokowski has been started (current session behavior).
3. **Is there a maximum age for keeping per-issue token data (to prevent memory leaks)?** → Reset when Stokowski restarts, and do not include issues older than 1 month.
