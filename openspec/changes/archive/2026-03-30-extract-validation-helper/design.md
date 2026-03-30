## Context

Currently, `runner.py` contains three runner functions (`run_agent_turn`, `run_codex_turn`, `run_mux_turn`) each with duplicated validation logic:

1. Check if `attempt.status == "streaming"`
2. Check if `proc.returncode == 0`
3. Call `validate_agent_output(attempt.full_output)`
4. Set status to "succeeded" or "failed" based on validation result

This ~15-line block is repeated identically in each function, violating DRY principles.

## Goals / Non-Goals

**Goals:**
- Extract common validation logic into a single helper function
- Ensure all three runners use identical validation behavior
- Reduce code duplication and maintenance burden
- Make future validation changes easier (change in one place)

**Non-Goals:**
- Changing validation logic or rules
- Modifying public APIs
- Adding new features
- Changing error messages (preserve existing behavior)

## Decisions

### Decision 1: Create `_finalize_attempt()` helper

**Rationale:** Encapsulates the common logic for:
- Determining final status from exit code
- Validating report presence
- Setting appropriate error messages

**Signature:**
```python
def _finalize_attempt(
    attempt: RunAttempt,
    returncode: int,
    stderr_output: str,
    issue_identifier: str,
) -> None:
    """Finalize attempt status based on exit code and report validation."""
```

### Decision 2: Keep validation function separate

`validate_agent_output()` remains as a standalone function for:
- Testability (can be unit tested independently)
- Potential reuse in other contexts
- Clear separation of concerns

## Risks / Trade-offs

- **Risk**: Introducing subtle behavior change during refactoring
  → Mitigation: Exact copy-paste of existing logic, no modifications
  → Add tests before refactoring to establish baseline

- **Risk**: Exception handling in helper could mask errors
  → Mitigation: Helper is pure logic (no IO), exceptions propagate naturally
