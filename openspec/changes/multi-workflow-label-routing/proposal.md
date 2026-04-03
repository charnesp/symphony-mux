## Why

Stokowski currently supports only a single state machine for all issues. Teams need different workflows for different ticket types (debug vs feature development) with distinct states, prompts, and review gates. Labels on Linear issues should route tickets to the appropriate workflow automatically.

## What Changes

- Add multi-workflow configuration support in `workflow.yaml` via new `workflows:` section
- Route issues to workflows based on Linear labels (e.g., label "debug" → debug workflow)
- Support workflow-scoped prompts (global_prompt, stage prompts per workflow)
- Update tracking comments to include workflow context for crash recovery
- Add workflow column to web dashboard
- **BREAKING**: None - existing single `states:` configuration remains compatible via automatic migration

## Capabilities

### New Capabilities
- `workflow-routing`: Route issues to workflows based on Linear labels with fallback default
- `workflow-config`: Parse and validate multi-workflow configuration from workflow.yaml
- `workflow-tracking`: Persist workflow context in Linear comments for state recovery

### Modified Capabilities
- `prompt-assembly`: Load global and stage prompts from workflow-scoped paths
- `dashboard`: Display workflow information in UI

## Impact

- **config.py**: New `WorkflowConfig` dataclass, workflow selection logic
- **orchestrator.py**: Dispatch-time workflow resolution, pass workflow to RunAttempt
- **prompt.py**: Workflow-scoped prompt loading
- **tracking.py**: Include workflow in tracking comments
- **web.py**: Dashboard displays workflow column
- **workflow.yaml**: New optional `workflows:` section (backwards compatible)
