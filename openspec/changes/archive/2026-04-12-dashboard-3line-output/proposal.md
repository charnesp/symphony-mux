## Why

The dashboard shows only ~1 line of agent output per card because `last_message` is truncated to 200 characters. The operator wants to see 3 lines of the agent's last message — which at the current font size means ~600 characters.

## What Changes

- Increase `last_message` truncation limit from 200 to 600 characters in the Claude runner's `_process_event()`
- Apply the same 600-char limit in the Codex and Mux runners (currently also 200)
- Update dashboard CSS to allow 3-line wrapping instead of single-line truncation with ellipsis

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- `agent-card-rendering`: Agent message area now displays up to 3 lines instead of 1
- `run-attempt-tracking`: `last_message` stores up to 600 chars instead of 200

## Impact

- `stokowski/runner.py`: Increase `last_message` truncation from `[:200]` to `[:600]` in all runners
- `stokowski/web.py`: Update `.agent-msg` CSS to allow 3-line wrapping
