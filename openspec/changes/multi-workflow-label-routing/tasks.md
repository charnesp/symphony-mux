## 1. Configuration Schema (config.py)

- [x] 1.1 Create WorkflowConfig dataclass with label, default, states, prompts fields
- [x] 1.2 Add workflows: Dict[str, WorkflowConfig] to ServiceConfig
- [x] 1.3 Implement get_workflow_for_issue(issue) method with label matching logic
- [x] 1.4 Add auto-migration: create implicit default workflow from root states: when workflows: absent
- [x] 1.5 Update parse_workflow_file to handle new workflows: section
- [x] 1.6 Add validate_workflows for cross-workflow validation (single default, labels unique)
- [x] 1.7 Add tests for workflow selection logic

## 2. Orchestrator Changes (orchestrator.py)

- [x] 2.1 Modify _dispatch() to call config.get_workflow_for_issue(issue)
- [x] 2.2 Add workflow field to RunAttempt dataclass
- [x] 2.3 Pass selected workflow to assemble_prompt() calls
- [x] 2.4 Pass selected workflow to tracking comment functions
- [x] 2.5 Handle "no matching workflow" error case with clear message

## 3. Prompt Assembly (prompt.py)

- [x] 3.1 Modify assemble_prompt() to accept optional workflow parameter
- [x] 3.2 Load global_prompt from workflow.prompts if workflow provided
- [x] 3.3 Ensure stage prompts resolve relative to workflow.yaml directory
- [x] 3.4 Maintain backwards compatibility for non-workflow calls

## 4. Tracking Comments (tracking.py)

- [x] 4.1 Add workflow parameter to make_state_comment()
- [x] 4.2 Add workflow parameter to make_gate_comment()
- [x] 4.3 Update parse_latest_tracking() to extract workflow from JSON
- [x] 4.4 Return workflow from parse_latest_tracking() for orchestrator use
- [x] 4.5 Handle legacy comments without workflow field (fallback to label routing)

## 5. Web Dashboard (web.py)

- [x] 5.1 Add workflow column to dashboard HTML template
- [x] 5.2 Include workflow in /api/v1/state JSON response
- [x] 5.3 Update dashboard JavaScript to display workflow column

## 6. Validation and Testing

- [x] 6.1 Create example workflow.yaml with multiple workflows for testing
- [x] 6.2 Test label-based routing with various label combinations
- [x] 6.3 Test default workflow fallback
- [x] 6.4 Verify backwards compatibility with single-workflow configs
- [x] 6.5 Run dry-run validation on new config format
- [x] 6.6 Test crash recovery with workflow in tracking comments

## 7. Documentation

- [x] 7.1 Update CLAUDE.md with multi-workflow configuration documentation
- [x] 7.2 Add example workflow.yaml showing workflows: section
- [x] 7.3 Document label-based routing behavior
- [x] 7.4 Document backwards compatibility guarantee
