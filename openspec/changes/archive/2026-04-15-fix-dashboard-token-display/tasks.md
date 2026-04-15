## 1. Orchestrator Token Tracking

- [ ] 1.1 Add `_issue_tokens` dictionary to Orchestrator `__init__` to track cumulative tokens per issue
- [ ] 1.2 Update `_on_worker_exit` to accumulate tokens into `_issue_tokens` for the issue
- [ ] 1.3 Add token cleanup when issues reach terminal states (in `_safe_transition` or similar)
- [ ] 1.4 Add `_issue_tokens_last_updated` to track last update timestamp for age filtering

## 2. State Snapshot Enhancement

- [ ] 2.1 Update `get_state_snapshot` to include cumulative token data for running issues
- [ ] 2.2 Add cumulative token data for issues at gates in the snapshot
- [ ] 2.3 Ensure run numbers from `_issue_state_runs` are properly exposed
- [ ] 2.4 Filter out token data for issues older than 1 month in `get_state_snapshot`

## 3. Dashboard JavaScript Fix

- [ ] 3.1 Update gate mapping in `renderAgents` to use actual token data from API instead of hardcoded 0
- [ ] 3.2 Verify running issues display correct cumulative tokens
- [ ] 3.3 Verify turn/run numbers display correctly

## 4. Testing

- [ ] 4.1 Verify token accumulation across multiple turns within a run
- [ ] 4.2 Verify gate-waiting issues show correct cumulative tokens
- [ ] 4.3 Verify terminal state clears token tracking
- [ ] 4.4 Run existing test suite to ensure no regressions

## 5. Documentation

- [ ] 5.1 Update CLAUDE.md if any new tracking behavior needs documentation
- [ ] 5.2 Add code comments explaining the token accumulation logic
