## ADDED Requirements

### Requirement: Route issues to workflows by label
The system SHALL route each Linear issue to exactly one workflow based on label matching.

#### Scenario: Issue with matching label
- **WHEN** an issue has label "debug"
- **AND** the configuration defines a workflow with `label: debug`
- **THEN** the issue SHALL be routed to that workflow

#### Scenario: Issue with no matching label uses default
- **WHEN** an issue has no labels matching any workflow's `label`
- **AND** one workflow is marked `default: true`
- **THEN** the issue SHALL be routed to the default workflow

#### Scenario: Issue with multiple labels uses first match
- **WHEN** an issue has labels ["feature", "debug"]
- **AND** YAML defines "feature" workflow before "debug" workflow
- **THEN** the issue SHALL be routed to the "feature" workflow (first match)

### Requirement: Validate workflow selection
The system SHALL fail dispatch with clear error if no workflow matches and no default exists.

#### Scenario: No matching workflow and no default
- **WHEN** an issue has labels ["unknown-label"]
- **AND** no workflow has `label: unknown-label` or `default: true`
- **THEN** dispatch SHALL fail with error "No workflow matches issue labels"

### Requirement: Store workflow in RunAttempt
The system SHALL store the selected workflow name in RunAttempt for the session lifetime.

#### Scenario: Dispatch stores workflow
- **WHEN** an issue is dispatched to workflow "debug"
- **THEN** RunAttempt SHALL include `workflow: "debug"`
- **AND** the workflow SHALL be passed to prompt and tracking functions
