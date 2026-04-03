# validation-helper Specification

## Purpose
TBD - created by archiving change extract-validation-helper. Update Purpose after archive.
## Requirements
### Requirement: Shared validation helper exists
The system SHALL provide a shared helper function `_finalize_attempt()` that encapsulates the common finalization logic for all agent runners.

#### Scenario: Helper finalizes successful attempt
- **WHEN** `_finalize_attempt()` is called with `returncode=0` and valid report
- **THEN** `attempt.status` SHALL be set to "succeeded"
- **AND** `attempt.error` SHALL be `None`

#### Scenario: Helper detects missing report
- **WHEN** `_finalize_attempt()` is called with `returncode=0` but missing report tags
- **THEN** `attempt.status` SHALL be set to "failed"
- **AND** `attempt.error` SHALL contain "Report validation failed"

#### Scenario: Helper handles process failure
- **WHEN** `_finalize_attempt()` is called with `returncode != 0`
- **THEN** `attempt.status` SHALL be set to "failed"
- **AND** `attempt.error` SHALL contain the exit code and stderr output

### Requirement: Validation rules are consistent
All agent runners (claude, codex, mux) SHALL use identical validation behavior via the shared helper.

#### Scenario: Claude runner uses shared helper
- **WHEN** `run_agent_turn()` completes successfully
- **THEN** it SHALL call `_finalize_attempt()` to set final status

#### Scenario: Codex runner uses shared helper
- **WHEN** `run_codex_turn()` completes successfully
- **THEN** it SHALL call `_finalize_attempt()` to set final status

#### Scenario: Mux runner uses shared helper
- **WHEN** `run_mux_turn()` completes successfully
- **THEN** it SHALL call `_finalize_attempt()` to set final status
