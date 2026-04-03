## Context

Currently, Stokowski supports a single state machine defined at the root of `workflow.yaml`. All issues in a project follow the same workflow path. Teams need different workflows for different types of work:

- **Debug workflow**: reproduce → fix → terminal (fast, minimal gates)
- **Feature workflow**: spec → build → review → terminal (structured, with code review gates)

Linear labels provide a natural routing mechanism. When an issue has label "debug", it should follow the debug workflow. Issues with label "feature" follow the feature workflow.

## Goals / Non-Goals

**Goals:**
- Support multiple named workflows in configuration
- Route issues to workflows based on Linear label matching
- Support per-workflow prompts (global and stage-specific)
- Persist workflow context in tracking comments for crash recovery
- Maintain backwards compatibility with existing single-workflow configs
- Display workflow information in web dashboard

**Non-Goals:**
- Dynamic workflow switching after issue dispatch (workflow is fixed at entry)
- Multiple workflows per issue (one issue = one workflow)
- Label pattern matching (exact label match only)
- Runtime workflow modification (config changes require restart)

## Decisions

### Decision: Label-based routing with default fallback
**Choice**: Route by exact label match, with optional `default: true` workflow as fallback.
**Rationale**: Linear labels are already fetched (`fetch_candidate_issues` includes labels). Exact match is simple and predictable. Default workflow ensures every issue gets routed even without matching labels.
**Alternative considered**: State-based routing (issue state determines workflow) - rejected because labels are more flexible and explicit intent markers.

### Decision: Workflow-scoped prompt paths
**Choice**: Each workflow defines its own `prompts.global_prompt` and stage `prompt` paths resolved relative to workflow.yaml.
**Rationale**: Keeps workflow assets together (e.g., `prompts/debug/`, `prompts/feature/`). Prevents naming collisions between workflows.
**Trade-off**: Slight duplication if workflows share prompts (operator can use symlinks or copy files).

### Decision: Workflow persistence in tracking comments
**Choice**: Include `workflow: <name>` in state/gate tracking comments.
**Rationale**: Enables crash recovery to resume with correct workflow even if config changes. Prevents workflow switching mid-session.
**Trade-off**: Slightly larger comments, but JSON is already compact.

### Decision: Backwards compatibility via auto-migration
**Choice**: If `workflows:` section is absent, create implicit "default" workflow from root `states:` and `prompts:`.
**Rationale**: Zero-config migration path for existing operators. Simplifies documentation (one concept, two syntaxes).

## Risks / Trade-offs

**[Risk]**: Workflow config validation becomes more complex (must validate multiple state machines).
**Mitigation**: Reuse existing validation logic per-workflow. Add cross-workflow checks (e.g., no duplicate default workflows).

**[Risk]**: Linear issue with multiple matching labels (e.g., both "debug" and "feature").
**Mitigation**: First match wins (YAML order). Document this behavior. Operator can use unique labels.

**[Risk]**: Changing workflow for in-flight issues requires manual tracking comment edits.
**Mitigation**: Document workflow immutability. Most use cases have clear ticket types upfront.

**[Trade-off]**: Config file becomes larger with multiple workflows.
**Acceptance**: Natural consequence of added flexibility. Operators can split prompt files to manage complexity.

## Migration Plan

1. **Phase 1**: Deploy code changes (backwards compatible, existing configs continue working)
2. **Phase 2**: Operators opt-in by adding `workflows:` section to workflow.yaml
3. **Phase 3**: (Optional) Deprecate root-level `states:` syntax in future major version

No breaking changes. Rollback: revert code, configs continue working.

## Open Questions

None - design is ready for implementation.
