## Purpose

Parse and validate multi-workflow configuration from workflow.yaml with backwards compatibility support.

## Requirements

### Requirement: Parse multi-workflow configuration
The system SHALL parse `workflows:` section from workflow.yaml into typed WorkflowConfig objects.

#### Scenario: Valid multi-workflow config
- **WHEN** workflow.yaml contains `workflows:` with "debug" and "feature" entries
- **THEN** ServiceConfig SHALL expose `workflows: Dict[str, WorkflowConfig]`
- **AND** each WorkflowConfig SHALL contain `label`, `default`, `states`, `prompts`

#### Scenario: Backwards compatibility with single workflow
- **WHEN** workflow.yaml contains root-level `states:` without `workflows:`
- **THEN** ServiceConfig SHALL create implicit "default" workflow from root config
- **AND** existing code using `config.states` SHALL continue working

### Requirement: Validate workflow configuration
The system SHALL validate each workflow independently and across workflows.

#### Scenario: Per-workflow validation
- **WHEN** validating workflow configuration
- **THEN** each workflow SHALL pass existing state machine validation (transitions exist, gates have rework_to, etc.)

#### Scenario: Cross-workflow validation
- **WHEN** multiple workflows define `default: true`
- **THEN** validation SHALL fail with error "Multiple default workflows defined"

#### Scenario: Missing label and not default
- **WHEN** a workflow has neither `label` nor `default: true`
- **THEN** validation SHALL fail with error "Workflow must have label or be marked default"

### Requirement: Resolve workflow prompts
The system SHALL resolve prompt paths relative to the workflow.yaml directory.

#### Scenario: Workflow-scoped global prompt
- **WHEN** a workflow defines `prompts.global_prompt: prompts/debug/global.md`
- **THEN** the system SHALL load from path relative to workflow.yaml directory

#### Scenario: Workflow-scoped stage prompt
- **WHEN** a state defines `prompt: prompts/debug/reproduce.md`
- **THEN** the system SHALL load from the resolved path

### Requirement: Parse agent-gate state type

The system SHALL accept `type: agent-gate` in workflow state definitions and SHALL represent it in `StateConfig` with the same execution-related fields as `agent` states (`prompt`, `linear_state`, `runner`, optional overrides) where applicable.

#### Scenario: Round-trip for agent-gate state

- **WHEN** workflow.yaml defines a state with `type: agent-gate` and a `prompt` path
- **THEN** parsing SHALL produce a `StateConfig` with `type` equal to `agent-gate`
- **AND** the `prompt` path SHALL be preserved for prompt loading

### Requirement: Validate agent-gate transitions and default

The system SHALL require that every `agent-gate` state defines a non-empty `transitions` map, a mandatory `default_transition` string that matches a key in that map, that every transition target names an existing state in the same workflow (or root state machine in legacy mode), and that the target state of `default_transition` has `type: gate` (human validation path for routing failures).

#### Scenario: Missing default_transition fails validation

- **WHEN** a state has `type: agent-gate` and `transitions` with at least one entry
- **AND** `default_transition` is absent or empty
- **THEN** validation SHALL fail with an explicit error

#### Scenario: default_transition not in transitions fails validation

- **WHEN** `default_transition` is set to `clean`
- **AND** `transitions` has no key `clean`
- **THEN** validation SHALL fail with an explicit error

#### Scenario: Unknown transition target fails validation

- **WHEN** an `agent-gate` state maps `has_findings` to a state name not defined in the workflow
- **THEN** validation SHALL fail with an explicit error

#### Scenario: default_transition target must be a gate

- **WHEN** an `agent-gate` state has `default_transition: clean`
- **AND** `transitions.clean` names an `agent` or `terminal` state
- **THEN** validation SHALL fail with an explicit error stating that the default routing target must be `type: gate`

### Requirement: State machine validation includes agent-gate

Per-workflow validation SHALL run the new `agent-gate` rules alongside existing checks for `agent`, `gate`, and `terminal` states without weakening existing gate or agent rules.

#### Scenario: Mixed workflow passes

- **WHEN** a workflow contains only valid `agent`, `gate`, `terminal`, and `agent-gate` states with consistent transitions
- **THEN** validation SHALL succeed
