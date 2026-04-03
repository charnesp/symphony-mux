## ADDED Requirements

### Requirement: Include workflow in state tracking comments
The system SHALL include the workflow name in state tracking comments.

#### Scenario: State entry comment includes workflow
- **WHEN** creating a state tracking comment
- **THEN** the hidden JSON SHALL include `"workflow": "debug"`
- **AND** the human-readable text SHALL indicate the workflow

### Requirement: Include workflow in gate tracking comments
The system SHALL include the workflow name in gate tracking comments.

#### Scenario: Gate waiting comment includes workflow
- **WHEN** creating a gate tracking comment with status "waiting"
- **THEN** the hidden JSON SHALL include `"workflow": "feature"`

### Requirement: Parse workflow from tracking comments
The system SHALL extract workflow from tracking comments for crash recovery.

#### Scenario: Recovery from tracking comment
- **WHEN** parsing latest tracking comment containing `"workflow": "debug"`
- **THEN** parse_latest_tracking SHALL return `workflow: "debug"`
- **AND** the orchestrator SHALL use this workflow for the issue

#### Scenario: Fallback for legacy comments without workflow
- **WHEN" parsing a tracking comment without `workflow` field
- **THEN** the system SHALL use label-based routing to determine workflow
- **AND** subsequent comments SHALL include the resolved workflow
