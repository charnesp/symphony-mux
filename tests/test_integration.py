"""Integration tests for multi-workflow functionality.

These tests validate:
- Label-based routing with various combinations
- Default workflow fallback
- Backwards compatibility with single-workflow configs
"""

from dataclasses import dataclass, field

import pytest

from stokowski.config import (
    parse_workflow_file,
)


@dataclass
class MockIssue:
    """Mock Linear issue."""

    id: str = "issue-1"
    identifier: str = "TEST-1"
    title: str = "Test"
    labels: list[str] = field(default_factory=list)


class TestLabelBasedRouting:
    """Test various label combinations for routing (6.2)."""

    def test_single_matching_label(self, tmp_path):
        """Issue with single matching label routes correctly."""
        yaml_content = """
tracker:
  project_slug: test

workflows:
  debug:
    label: debug
    states:
      reproduce: {type: agent}
  feature:
    label: feature
    states:
      spec: {type: agent}
"""
        wf_file = tmp_path / "workflow.yaml"
        wf_file.write_text(yaml_content)

        result = parse_workflow_file(wf_file)
        cfg = result.config

        # Test debug label
        debug_issue = MockIssue(labels=["debug"])
        assert cfg.get_workflow_for_issue(debug_issue).name == "debug"

        # Test feature label
        feature_issue = MockIssue(labels=["feature"])
        assert cfg.get_workflow_for_issue(feature_issue).name == "feature"

    def test_multiple_labels_with_match(self, tmp_path):
        """Issue with multiple labels where one matches."""
        yaml_content = """
tracker:
  project_slug: test

workflows:
  debug:
    label: debug
    states:
      reproduce: {type: agent}
  default:
    default: true
    states:
      task: {type: agent}
"""
        wf_file = tmp_path / "workflow.yaml"
        wf_file.write_text(yaml_content)

        result = parse_workflow_file(wf_file)
        cfg = result.config

        # Issue has multiple labels, one matches
        issue = MockIssue(labels=["urgent", "debug", "backend"])
        wf = cfg.get_workflow_for_issue(issue)
        assert wf.name == "debug"

    def test_no_matching_labels_with_default(self, tmp_path):
        """Issue with no matching labels falls back to default (6.3)."""
        yaml_content = """
tracker:
  project_slug: test

workflows:
  debug:
    label: debug
    states:
      reproduce: {type: agent}
  general:
    default: true
    states:
      task: {type: agent}
"""
        wf_file = tmp_path / "workflow.yaml"
        wf_file.write_text(yaml_content)

        result = parse_workflow_file(wf_file)
        cfg = result.config

        # Issue with unrelated labels
        issue = MockIssue(labels=["documentation", "help-wanted"])
        wf = cfg.get_workflow_for_issue(issue)
        assert wf.name == "general"
        assert wf.default is True

    def test_case_sensitive_labels(self, tmp_path):
        """Label matching should be case-sensitive."""
        yaml_content = """
tracker:
  project_slug: test

workflows:
  debug:
    label: Debug
    states:
      reproduce: {type: agent}
  default:
    default: true
    states:
      task: {type: agent}
"""
        wf_file = tmp_path / "workflow.yaml"
        wf_file.write_text(yaml_content)

        result = parse_workflow_file(wf_file)
        cfg = result.config

        # "debug" (lowercase) should not match "Debug" (capitalized)
        issue = MockIssue(labels=["debug"])
        wf = cfg.get_workflow_for_issue(issue)
        # Falls back to default since "debug" != "Debug"
        assert wf.name == "default"


class TestBackwardsCompatibility:
    """Test backwards compatibility with single-workflow configs (6.4)."""

    def test_legacy_config_no_workflows_section(self, tmp_path):
        """Legacy config without workflows section still works."""
        yaml_content = """
tracker:
  project_slug: test
  api_key: test-key

states:
  reproduce:
    type: agent
    prompt: prompts/reproduce.md
    transitions:
      success: fix
  fix:
    type: agent
    prompt: prompts/fix.md
    transitions:
      success: terminal
  terminal:
    type: terminal

prompts:
  global_prompt: prompts/global.md
"""
        wf_file = tmp_path / "workflow.yaml"
        wf_file.write_text(yaml_content)

        result = parse_workflow_file(wf_file)
        cfg = result.config

        # No workflows section
        assert cfg.workflows == {}

        # Root states should be populated
        assert "reproduce" in cfg.states
        assert "fix" in cfg.states

        # get_workflow_for_issue creates implicit default
        issue = MockIssue(labels=["anything"])
        wf = cfg.get_workflow_for_issue(issue)
        assert wf.name == "default"
        assert wf.default is True
        assert "reproduce" in wf.states

    def test_legacy_config_with_workflow_transitions(self, tmp_path):
        """Legacy state transitions are preserved."""
        yaml_content = """
tracker:
  project_slug: test

states:
  reproduce:
    type: agent
    transitions:
      success: fix
      failure: terminal
  fix:
    type: agent
    transitions:
      success: terminal
  terminal:
    type: terminal
"""
        wf_file = tmp_path / "workflow.yaml"
        wf_file.write_text(yaml_content)

        result = parse_workflow_file(wf_file)
        cfg = result.config

        issue = MockIssue(labels=[])
        wf = cfg.get_workflow_for_issue(issue)

        # Transitions should be preserved
        assert wf.states["reproduce"].transitions == {"success": "fix", "failure": "terminal"}
        assert wf.states["fix"].transitions == {"success": "terminal"}


class TestConfigValidation:
    """Test config validation (6.5)."""

    def test_multiple_defaults_validation(self, tmp_path):
        """Should handle config with multiple default workflows."""
        yaml_content = """
tracker:
  project_slug: test

workflows:
  debug:
    label: debug
    default: true
    states:
      reproduce: {type: agent}
  feature:
    label: feature
    default: true
    states:
      spec: {type: agent}
"""
        wf_file = tmp_path / "workflow.yaml"
        wf_file.write_text(yaml_content)

        # Parsing should succeed
        result = parse_workflow_file(wf_file)
        cfg = result.config

        # Both marked as default
        assert cfg.workflows["debug"].default is True
        assert cfg.workflows["feature"].default is True

        # get_default_workflow_name returns first one
        assert cfg.get_default_workflow_name() == "debug"

    def test_workflow_without_label_or_default(self, tmp_path):
        """Workflow without label or default flag."""
        yaml_content = """
tracker:
  project_slug: test

workflows:
  unnamed:
    states:
      task: {type: agent}
"""
        wf_file = tmp_path / "workflow.yaml"
        wf_file.write_text(yaml_content)

        result = parse_workflow_file(wf_file)
        cfg = result.config

        # Workflow has no label and is not default
        assert cfg.workflows["unnamed"].label is None
        assert cfg.workflows["unnamed"].default is False

        # Any issue without matching labels will fail routing
        issue = MockIssue(labels=["anything"])
        with pytest.raises(ValueError):
            cfg.get_workflow_for_issue(issue)


class TestWorkflowPersistence:
    """Test workflow persistence in tracking (6.6)."""

    def test_workflow_in_state_comment(self):
        """State tracking comment should include workflow."""
        from stokowski.tracking import make_state_comment

        comment = make_state_comment(state="reproduce", run=1, workflow="debug")

        assert '"workflow": "debug"' in comment
        assert "[debug]" in comment  # Human-readable part

    def test_workflow_in_gate_comment(self):
        """Gate tracking comment should include workflow."""
        from stokowski.tracking import make_gate_comment

        comment = make_gate_comment(
            state="review",
            status="waiting",
            run=1,
            workflow="feature",
        )

        assert '"workflow": "feature"' in comment

    def test_parse_tracking_with_workflow(self):
        """Should extract workflow from tracking comment."""
        from stokowski.tracking import parse_latest_tracking

        comment_body = """Some human text

<!-- stokowski:state {"state": "reproduce", "run": 1, "timestamp": "2024-01-01T00:00:00+00:00", "workflow": "debug"} -->

**[Stokowski]** Entering state: **reproduce** [debug] (run 1)
"""
        comment = {"body": comment_body, "createdAt": "2024-01-01T00:00:00Z"}

        result = parse_latest_tracking([comment])

        assert result is not None
        assert result.get("workflow") == "debug"
        assert result.get("state") == "reproduce"

    def test_parse_tracking_without_workflow_legacy(self):
        """Should handle legacy comments without workflow field."""
        from stokowski.tracking import parse_latest_tracking

        comment_body = """<!-- stokowski:state {"state": "reproduce", "run": 1, "timestamp": "2024-01-01T00:00:00+00:00"} -->

**[Stokowski]** Entering state: **reproduce** (run 1)
"""
        comment = {"body": comment_body, "createdAt": "2024-01-01T00:00:00Z"}

        result = parse_latest_tracking([comment])

        assert result is not None
        assert result.get("state") == "reproduce"
        assert "workflow" not in result or result.get("workflow") is None

    @pytest.mark.asyncio
    async def test_crash_recovery_legacy_default_to_explicit_default(self, tmp_path):
        """Crash recovery: legacy 'default' workflow name routes to explicit default."""
        from stokowski.orchestrator import Orchestrator

        yaml_content = """
tracker:
  project_slug: test

workflows:
  debug:
    label: debug
    states:
      reproduce: {type: agent}
  general:
    default: true
    states:
      task: {type: agent}
"""
        wf_file = tmp_path / "workflow.yaml"
        wf_file.write_text(yaml_content)

        # Create orchestrator with the workflow
        orch = Orchestrator(wf_file)
        orch.workflow = parse_workflow_file(wf_file)

        # Simulate a tracking dict from a legacy comment with workflow: "default"
        tracking = {"workflow": "default", "state": "task", "run": 1}

        # Create a mock issue
        issue = MockIssue(id="issue-123", identifier="TEST-123", labels=[])

        # Call the method under test
        result = await orch._resolve_workflow_for_issue(issue, tracking)  # type: ignore[arg-type]

        # Should return the explicit default workflow (general)
        assert result is not None
        assert result.name == "general"
        assert result.default is True

    @pytest.mark.asyncio
    async def test_crash_recovery_legacy_default_no_explicit_default(self, tmp_path):
        """Crash recovery: legacy 'default' with no explicit default falls through."""
        from stokowski.orchestrator import Orchestrator

        yaml_content = """
tracker:
  project_slug: test

workflows:
  debug:
    label: debug
    states:
      reproduce: {type: agent}
  feature:
    label: feature
    states:
      spec: {type: agent}
"""
        wf_file = tmp_path / "workflow.yaml"
        wf_file.write_text(yaml_content)

        orch = Orchestrator(wf_file)
        orch.workflow = parse_workflow_file(wf_file)

        # Legacy tracking with workflow: "default"
        tracking = {"workflow": "default", "state": "reproduce", "run": 1}

        # Issue with matching label (debug)
        issue = MockIssue(id="issue-123", identifier="TEST-123", labels=["debug"])

        result = await orch._resolve_workflow_for_issue(issue, tracking)  # type: ignore[arg-type]

        # No explicit default, so falls through to label-based routing
        assert result is not None
        assert result.name == "debug"


class TestWorkflowScoping:
    """Test workflow-scoped configuration."""

    def test_workflow_isolated_states(self, tmp_path):
        """Each workflow has isolated state definitions."""
        yaml_content = """
tracker:
  project_slug: test

workflows:
  debug:
    label: debug
    states:
      reproduce:
        type: agent
        prompt: prompts/debug/reproduce.md
      fix:
        type: agent
        prompt: prompts/debug/fix.md

  feature:
    label: feature
    states:
      spec:
        type: agent
        prompt: prompts/feature/spec.md
      build:
        type: agent
        prompt: prompts/feature/build.md
"""
        wf_file = tmp_path / "workflow.yaml"
        wf_file.write_text(yaml_content)

        result = parse_workflow_file(wf_file)
        cfg = result.config

        debug_wf = cfg.workflows["debug"]
        feature_wf = cfg.workflows["feature"]

        # States are isolated per workflow
        assert "reproduce" in debug_wf.states
        assert "spec" in feature_wf.states
        assert "reproduce" not in feature_wf.states
        assert "spec" not in debug_wf.states

        # Prompts are scoped
        assert debug_wf.states["reproduce"].prompt == "prompts/debug/reproduce.md"
        assert feature_wf.states["spec"].prompt == "prompts/feature/spec.md"

    def test_workflow_scoped_prompts(self, tmp_path):
        """Each workflow has its own prompts config."""
        yaml_content = """
tracker:
  project_slug: test

workflows:
  debug:
    label: debug
    states:
      reproduce: {type: agent}
    prompts:
      global_prompt: prompts/debug/global.md
      lifecycle_prompt: prompts/debug/lifecycle.md

  feature:
    label: feature
    states:
      spec: {type: agent}
    prompts:
      global_prompt: prompts/feature/global.md
"""
        wf_file = tmp_path / "workflow.yaml"
        wf_file.write_text(yaml_content)

        result = parse_workflow_file(wf_file)
        cfg = result.config

        assert cfg.workflows["debug"].prompts.global_prompt == "prompts/debug/global.md"
        assert cfg.workflows["feature"].prompts.global_prompt == "prompts/feature/global.md"

        # Feature uses default lifecycle_prompt
        assert cfg.workflows["feature"].prompts.lifecycle_prompt == "prompts/lifecycle.md"
