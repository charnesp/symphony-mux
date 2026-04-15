## ADDED Requirements

### Requirement: Agent-gate executes one runner turn then routes by structured output

The system SHALL treat states with `type: agent-gate` as agent-like for execution (same runner, hooks, and prompt assembly as `type: agent`) for exactly one successful turn per dispatch in state-machine mode, then SHALL select the next state from configured named transitions using a structured routing payload in the agent output.

#### Scenario: Successful parse selects a declared transition

- **WHEN** an issue completes a runner turn in state `review-router` of type `agent-gate`
- **AND** `transitions` contains `has_findings: correct-review` and `clean: human-validation`
- **AND** `default_transition` is `clean`
- **AND** the agent output contains a valid `<<<STOKOWSKI_ROUTE>>>` block with `{"transition": "has_findings"}`
- **THEN** the system SHALL invoke the state transition named `has_findings`
- **AND** the issue’s workflow state SHALL become `correct-review`
- **AND** the system SHALL NOT post an agent-gate routing-error comment for this completion

#### Scenario: Rationale report is posted to the issue

- **WHEN** an issue completes an `agent-gate` turn with a valid routing payload
- **AND** the agent output contains a `<stokowski:report>...</stokowski:report>` block explaining the routing decision
- **THEN** the system SHALL post a Linear comment on the issue that includes that report content, using the same formatting approach as work reports for `type: agent` states
- **AND** the comment SHALL make the chosen transition legible to humans (e.g. in metadata or visible summary)

#### Scenario: Routing error posts issue comment and moves to human gate

- **WHEN** an issue completes a runner turn in an `agent-gate` state
- **AND** the routing block is absent or JSON is invalid or `transition` is not a key in `transitions`
- **THEN** the system SHALL post a Linear comment on the issue that states the category of routing failure (e.g. missing envelope, invalid JSON, unknown transition key) and sufficient detail for a human to act
- **AND** the system SHALL invoke the transition named by `default_transition`
- **AND** the next state SHALL be the human-validation `gate` configured as the target of `default_transition`

### Requirement: Routing marker and JSON shape

The system SHALL parse the routing decision from agent output by locating a `<<<STOKOWSKI_ROUTE>>>` / `<<<END_STOKOWSKI_ROUTE>>>` envelope and reading a single JSON object with a string field `transition`.

#### Scenario: Whitespace-tolerant envelope

- **WHEN** the envelope contains valid JSON with optional surrounding whitespace and newlines
- **THEN** parsing SHALL succeed and expose the `transition` string for lookup in `transitions`

### Requirement: Lifecycle exposes branch options to the agent

The system SHALL include in the assembled prompt for an `agent-gate` state the list of allowed transition keys and the required routing envelope format so the agent can emit a valid decision.

#### Scenario: Prompt lists transition keys

- **WHEN** `assemble_prompt` is called for an `agent-gate` state with transitions `has_findings` and `clean`
- **THEN** the assembled prompt SHALL mention both keys as valid `transition` values
- **AND** SHALL describe the `<<<STOKOWSKI_ROUTE>>>` / `<<<END_STOKOWSKI_ROUTE>>>` format
- **AND** SHALL require a `<stokowski:report>` block so the choice is documented in Linear comments

### Requirement: Agent-gate does not use human-gate fields

The system SHALL reject configuration where an `agent-gate` state defines `rework_to` or `max_rework` (those fields apply only to `type: gate`).

#### Scenario: Validation error for rework_to on agent-gate

- **WHEN** a state has `type: agent-gate` and a non-empty `rework_to`
- **THEN** configuration validation SHALL fail with a clear error referencing `agent-gate` and `rework_to`
