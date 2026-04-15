## ADDED Requirements

### Requirement: Per-issue cumulative token tracking
The system SHALL maintain cumulative token usage per issue across all turns within a run.

#### Scenario: Tokens accumulate across multiple turns
- **WHEN** an issue completes turn 1 consuming 500K tokens
- **AND** the same issue completes turn 2 consuming 700K tokens
- **THEN** the cumulative token count for that issue SHALL be 1.2M tokens

#### Scenario: Token data persists between turns
- **WHEN** an issue completes a turn and the attempt is removed from running
- **THEN** the cumulative token count SHALL be preserved for the next turn

### Requirement: Accurate dashboard token display for running issues
The system SHALL display the cumulative token count for currently running issues in the web dashboard.

#### Scenario: Running issue shows cumulative tokens
- **WHEN** an issue is currently running and has consumed 1.9M tokens across previous turns
- **THEN** the dashboard SHALL display "1.9M tok" for that issue

#### Scenario: New turn shows accumulated tokens from previous turns
- **WHEN** an issue starts turn 3 having consumed 800K tokens in turns 1-2
- **THEN** the dashboard SHALL display "800K tok" immediately (before turn 3 completes)

### Requirement: Accurate dashboard token display for issues at gates
The system SHALL display cumulative token counts for issues waiting at gates.

#### Scenario: Gate-waiting issue shows cumulative tokens
- **WHEN** an issue is waiting at a gate state
- **AND** the issue has consumed 1.5M tokens in previous turns
- **THEN** the dashboard SHALL display "1.5M tok" for that issue

### Requirement: Accurate run number display
The system SHALL display the correct run number (from `_issue_state_runs`) in the dashboard.

#### Scenario: Issue on run 2 displays run 2
- **WHEN** an issue has completed run 1 and is now on run 2
- **THEN** the dashboard SHALL display "turn 2" (or equivalent run indicator)

#### Scenario: Issue at gate shows correct run number
- **WHEN** an issue is waiting at a gate on run 3
- **THEN** the dashboard SHALL display "turn 3" for that issue

### Requirement: Token data cleanup on terminal state
The system SHALL clear per-issue token tracking when an issue reaches a terminal state.

#### Scenario: Terminal state clears token tracking
- **WHEN** an issue reaches a terminal state
- **THEN** the cumulative token tracking for that issue SHALL be removed
- **AND** the memory SHALL be freed
