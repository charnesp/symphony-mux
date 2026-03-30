## 1. Create Shared Helper

- [x] 1.1 Add `_finalize_attempt()` function in `stokowski/runner.py` after `validate_agent_output()`
- [x] 1.2 Implement logic to check `returncode == 0` and validate report
- [x] 1.3 Set `attempt.status` and `attempt.error` appropriately
- [x] 1.4 Add docstring explaining function purpose and parameters

## 2. Refactor Claude Runner

- [x] 2.1 In `run_agent_turn()`, replace validation block with call to `_finalize_attempt()`
- [x] 2.2 Verify `stderr_output` variable is available for the helper call
- [x] 2.3 Ensure no change in behavior (preserve error messages)

## 3. Refactor Codex Runner

- [x] 3.1 In `run_codex_turn()`, replace validation block with call to `_finalize_attempt()`
- [x] 3.2 Verify `stderr_output` variable is available for the helper call
- [x] 3.3 Ensure no change in behavior (preserve error messages)

## 4. Refactor Mux Runner

- [x] 4.1 In `run_mux_turn()`, replace validation block with call to `_finalize_attempt()`
- [x] 4.2 Verify `stderr_output` variable is available for the helper call
- [x] 4.3 Ensure no change in behavior (preserve error messages)

## 5. Verification

- [x] 5.1 Run Python syntax check on `stokowski/runner.py`
- [x] 5.2 Review all three runner functions to ensure identical behavior
- [x] 5.3 Verify no code duplication remains between runners
- [x] 5.4 Commit changes with descriptive message
