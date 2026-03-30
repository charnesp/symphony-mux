## ADDED Requirements

### Requirement: Lifecycle content externalization
ALL lifecycle section content SHALL reside in external Markdown template files. The `build_lifecycle_section()` function SHALL NOT contain any hardcoded content strings.

#### Scenario: Lifecycle loaded from file
- **WHEN** `assemble_prompt()` calls `build_lifecycle_section()`
- **THEN** the function SHALL load the template from the configured file path
- **AND** render it with Jinja2 context
- **AND** return the rendered content
- **AND** NO hardcoded strings SHALL be used in the Python code

#### Scenario: Missing lifecycle file
- **WHEN** the lifecycle template file is missing
- **THEN** the system SHALL raise `FileNotFoundError` with a clear error message
- **AND** the error SHALL indicate the expected file path

### Requirement: Template context variables
The lifecycle template SHALL receive all necessary context variables for rendering dynamic content.

#### Scenario: Available template variables
- **WHEN** rendering the lifecycle template
- **THEN** the following variables SHALL be available:
  - `issue` - full Issue object with all attributes
  - `state_name` - current state name
  - `state_cfg` - StateConfig for current state
  - `linear_states` - LinearStatesConfig
  - `workflow_states` - dict of all workflow states
  - `run` - run number
  - `is_rework` - boolean for rework status
  - `recent_comments` - list of recent comments
  - `previous_error` - previous error message
  - `transitions` - available transitions

### Requirement: Default template location
The system SHALL provide a default lifecycle template at `prompts/lifecycle.md`.

#### Scenario: Default configuration
- **GIVEN** no `lifecycle_prompt` explicitly configured
- **WHEN** the system loads configuration
- **THEN** it SHALL default to `prompts/lifecycle.md`

### Requirement: Simplified build function
The `build_lifecycle_section()` function SHALL be simplified to only load and render the template.

#### Scenario: No hardcoded content
- **WHEN** inspecting `build_lifecycle_section()` source code
- **THEN** there SHALL be NO string literals containing markdown content
- **AND** NO string concatenation building output lines
- **AND** the function SHALL only load file, render template, and return result
