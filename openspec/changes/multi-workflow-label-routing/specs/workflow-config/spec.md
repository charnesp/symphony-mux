## ADDED Requirements

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
- **WHEN" validating workflow configuration
- **THEN** each workflow SHALL pass existing state machine validation (transitions exist, gates have rework_to, etc.)

#### Scenario: Cross-workflow validation
- **WHEN" multiple workflows define `default: true`
- **THEN" validation SHALL fail with error "Multiple default workflows defined"

#### Scenario: Missing label and not default
- **WHEN" a workflow has neither `label` nor `default: true`
- **THEN** validation SHALL fail with error "Workflow must have label or be marked default"

### Requirement: Resolve workflow prompts
The system SHALL resolve prompt paths relative to the workflow.yaml directory.

#### Scenario: Workflow-scoped global prompt
- **WHEN" a workflow defines `prompts.global_prompt: prompts/debug/global.md`
- **THEN** the system SHALL load from path relative to workflow.yaml directory

#### Scenario: Workflow-scoped stage prompt
- **WHEN** a state defines `prompt: prompts/debug/reproduce.md`
- **THEN** the system SHALL load from the resolved path
