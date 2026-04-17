# Implementation Tasks: `common_prompts` Support

## Tasks

### Task 1: Add `merge_with_defaults` method to PromptsConfig
**File**: `stokowski/config.py`

Add a method to `PromptsConfig` that merges workflow-specific prompts with common defaults:

```python
def merge_with_defaults(self, defaults: PromptsConfig) -> PromptsConfig:
    """Return new PromptsConfig with values from self overriding defaults."""
    return PromptsConfig(
        global_prompt=self.global_prompt if self.global_prompt is not None else defaults.global_prompt,
        lifecycle_prompt=self.lifecycle_prompt if self.lifecycle_prompt != "prompts/lifecycle.md" or defaults.lifecycle_prompt == "prompts/lifecycle.md" else defaults.lifecycle_prompt,
        lifecycle_post_run_prompt=self.lifecycle_post_run_prompt if self.lifecycle_post_run_prompt is not None else defaults.lifecycle_post_run_prompt,
    )
```

**Validation**:
- Method correctly handles `None` values
- Method correctly handles default lifecycle_prompt value

---

### Task 2: Add `common_prompts` field to ServiceConfig
**File**: `stokowski/config.py`

Add the `common_prompts` field to the `ServiceConfig` dataclass:

```python
@dataclass
class ServiceConfig:
    tracker: TrackerConnectionConfig = field(default_factory=TrackerConnectionConfig)
    polling: PollingConfig = field(default_factory=PollingConfig)
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    hooks: HooksConfig = field(default_factory=HooksConfig)
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    linear_states: LinearStatesConfig = field(default_factory=LinearStatesConfig)
    common_prompts: PromptsConfig = field(default_factory=PromptsConfig)  # NEW
    prompts: PromptsConfig = field(default_factory=PromptsConfig)
    states: dict[str, StateConfig] = field(default_factory=lambda: {})
    workflows: dict[str, WorkflowConfig] = field(default_factory=lambda: {})
```

---

### Task 3: Parse `common_prompts` in `parse_workflow_file()`
**File**: `stokowski/config.py`

Add parsing logic for the root-level `common_prompts` section:

1. After parsing the root `prompts` section, add:
```python
# Parse common_prompts (defaults for all workflows)
cp_raw: dict[str, Any] = config_raw.get("common_prompts", {}) or {}
common_prompts = PromptsConfig(
    global_prompt=cp_raw.get("global_prompt"),
    lifecycle_prompt=str(cp_raw.get("lifecycle_prompt", "prompts/lifecycle.md")),
    lifecycle_post_run_prompt=cp_raw.get("lifecycle_post_run_prompt"),
)
```

2. Pass `common_prompts` to the ServiceConfig constructor

---

### Task 4: Merge common_prompts with workflow prompts
**File**: `stokowski/config.py`

Modify the workflow parsing section to merge prompts:

In the workflows loop, replace:
```python
wf_prompts = PromptsConfig(
    global_prompt=wf_prompts_raw.get("global_prompt"),
    lifecycle_prompt=str(wf_prompts_raw.get("lifecycle_prompt", "prompts/lifecycle.md")),
    lifecycle_post_run_prompt=wf_prompts_raw.get("lifecycle_post_run_prompt"),
)
```

With:
```python
wf_prompts_explicit = PromptsConfig(
    global_prompt=wf_prompts_raw.get("global_prompt"),
    lifecycle_prompt=str(wf_prompts_raw.get("lifecycle_prompt", "prompts/lifecycle.md")),
    lifecycle_post_run_prompt=wf_prompts_raw.get("lifecycle_post_run_prompt"),
)
# Merge with common_prompts - workflow takes precedence
wf_prompts = wf_prompts_explicit.merge_with_defaults(common_prompts)
```

---

### Task 5: Update example workflow configuration
**File**: `workflow.example.yaml`

Update the example to demonstrate the new feature:

```yaml
# Common prompts shared across all workflows
common_prompts:
  lifecycle_prompt: prompts/lifecycle.md
  lifecycle_post_run_prompt: prompts/lifecycle-post-run.md

workflows:
  debug:
    label: debug
    prompts:
      global_prompt: prompts/debug/global.md
      # lifecycle_prompt and lifecycle_post_run_prompt inherited

  feature:
    label: feature
    default: true
    prompts:
      global_prompt: prompts/feature/global.md
      # lifecycle_prompt and lifecycle_post_run_prompt inherited
```

---

### Task 6: Run tests and validate
**Command**: `uv run pytest tests/ -v`

Ensure:
- All existing tests pass
- No regressions in config parsing

---

## Verification Checklist

- [x] `common_prompts` section can be parsed from YAML
- [x] Workflows inherit unspecified prompts from `common_prompts`
- [x] Workflow-specific prompts override `common_prompts` values
- [x] Existing configs without `common_prompts` continue to work
- [x] All tests pass
