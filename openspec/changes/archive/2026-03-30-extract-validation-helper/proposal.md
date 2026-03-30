## Why

The report validation logic (`validate_agent_output`) is currently duplicated across three runner functions in `runner.py` (`run_agent_turn`, `run_codex_turn`, `run_mux_turn`). This creates a maintenance burden - any change to validation rules requires updates in three places, increasing the risk of inconsistencies and bugs.

## What Changes

- Extract `validate_agent_output()` and validation-result-handling logic into a shared helper function `_finalize_attempt()`
- Update all three runners (claude, codex, mux) to use the shared helper
- Remove duplicated validation blocks from each runner
- **No breaking changes** - public API remains unchanged

## Capabilities

### New Capabilities
- `validation-helper`: Shared validation and finalization logic for agent runner output

### Modified Capabilities
- None - this is a pure refactoring with no requirement changes

## Impact

- **Code**: `stokowski/runner.py` - refactoring only
- **API**: No changes to public interfaces
- **Dependencies**: None
- **Systems**: Agent runner subsystem
