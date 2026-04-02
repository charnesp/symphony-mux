"""Tests for multi-workflow routing functionality."""

from dataclasses import dataclass, field
from typing import Any

from stokowski.config import (
    ServiceConfig,
    WorkflowConfig,
    StateConfig,
    PromptsConfig,
    parse_workflow_file,
)


@dataclass
class MockIssue:
    """Mock Linear issue for testing."""
    id: str = "issue-1"
    identifier: str = "TEST-1"
    title: str = "Test Issue"
    labels: list[str] = field(default_factory=list)


class TestWorkflowRouting:
    """Tests for workflow routing by label."""

    def test_route_by_exact_label_match(self):
        """Issue with label 'debug' should route to debug workflow."""
        debug_wf = WorkflowConfig(
            name="debug",
            label="debug",
            states={"reproduce": StateConfig(name="reproduce", type="agent")},
        )
        feature_wf = WorkflowConfig(
            name="feature",
            label="feature",
            states={"spec": StateConfig(name="spec", type="agent")},
        )

        cfg = ServiceConfig()
        cfg.workflows = {"debug": debug_wf, "feature": feature_wf}

        issue = MockIssue(labels=["debug"])
        result = cfg.get_workflow_for_issue(issue)

        assert result.name == "debug"
        assert "reproduce" in result.states

    def test_route_by_first_match_with_multiple_labels(self):
        """First matching workflow wins when issue has multiple labels."""
        debug_wf = WorkflowConfig(name="debug", label="debug", states={})
        feature_wf = WorkflowConfig(name="feature", label="feature", states={})

        cfg = ServiceConfig()
        cfg.workflows = {
            "debug": debug_wf,  # First in dict
            "feature": feature_wf,
        }

        issue = MockIssue(labels=["feature", "debug"])
        result = cfg.get_workflow_for_issue(issue)

        # First match (debug) should win
        assert result.name == "debug"

    def test_fallback_to_default_workflow(self):
        """Should use default workflow when no label matches."""
        debug_wf = WorkflowConfig(name="debug", label="debug", states={})
        default_wf = WorkflowConfig(name="default", default=True, states={"task": StateConfig()})

        cfg = ServiceConfig()
        cfg.workflows = {"debug": debug_wf, "default": default_wf}

        issue = MockIssue(labels=["unknown-label"])
        result = cfg.get_workflow_for_issue(issue)

        assert result.name == "default"
        assert result.default is True

    def test_error_when_no_match_and_no_default(self):
        """Should raise ValueError when no workflow matches and no default."""
        cfg = ServiceConfig()
        cfg.workflows = {
            "debug": WorkflowConfig(name="debug", label="debug", states={}),
        }

        issue = MockIssue(labels=["unknown-label"])

        try:
            cfg.get_workflow_for_issue(issue)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "No workflow matches issue labels" in str(e)

    def test_legacy_mode_single_workflow(self):
        """Legacy configs without workflows section create implicit default."""
        cfg = ServiceConfig()
        cfg.states = {"reproduce": StateConfig(name="reproduce", type="agent")}
        cfg.prompts = PromptsConfig(global_prompt="prompts/global.md")
        # No workflows section

        issue = MockIssue(labels=["anything"])
        result = cfg.get_workflow_for_issue(issue)

        assert result.name == "default"
        assert result.default is True
        assert len(result.states) == 1
        assert result.prompts.global_prompt == "prompts/global.md"

    def test_empty_labels_fallback_to_default(self):
        """Issue with no labels should fallback to default workflow."""
        cfg = ServiceConfig()
        cfg.workflows = {
            "debug": WorkflowConfig(name="debug", label="debug", states={}),
            "default": WorkflowConfig(name="default", default=True, states={"task": StateConfig()}),
        }

        issue = MockIssue(labels=[])
        result = cfg.get_workflow_for_issue(issue)

        assert result.name == "default"

    def test_none_labels_fallback_to_default(self):
        """Issue with None labels should fallback to default workflow."""
        cfg = ServiceConfig()
        cfg.workflows = {
            "default": WorkflowConfig(name="default", default=True, states={"task": StateConfig()}),
        }

        issue = MockIssue()
        issue.labels = None  # type: ignore
        result = cfg.get_workflow_for_issue(issue)

        assert result.name == "default"


class TestParseMultiWorkflowConfig:
    """Tests for parsing multi-workflow YAML configuration."""

    def test_parse_workflows_section(self, tmp_path):
        """Should parse workflows section from YAML file."""
        yaml_content = """
tracker:
  project_slug: test-project

workflows:
  debug:
    label: debug
    states:
      reproduce:
        type: agent
        prompt: prompts/debug/reproduce.md
        transitions:
          success: fix
    prompts:
      global_prompt: prompts/debug/global.md

  feature:
    label: feature
    default: true
    states:
      spec:
        type: agent
    prompts:
      global_prompt: prompts/feature/global.md
"""
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text(yaml_content)

        result = parse_workflow_file(workflow_file)

        assert "debug" in result.config.workflows
        assert "feature" in result.config.workflows

        debug_wf = result.config.workflows["debug"]
        assert debug_wf.label == "debug"
        assert debug_wf.default is False
        assert "reproduce" in debug_wf.states

        feature_wf = result.config.workflows["feature"]
        assert feature_wf.label == "feature"
        assert feature_wf.default is True
        assert "spec" in feature_wf.states

    def test_workflow_scoped_prompts(self, tmp_path):
        """Each workflow should have its own prompts config."""
        yaml_content = """
tracker:
  project_slug: test-project

workflows:
  debug:
    label: debug
    states:
      reproduce:
        type: agent
    prompts:
      global_prompt: prompts/debug/global.md
      lifecycle_prompt: prompts/debug/lifecycle.md
"""
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text(yaml_content)

        result = parse_workflow_file(workflow_file)

        debug_wf = result.config.workflows["debug"]
        assert debug_wf.prompts.global_prompt == "prompts/debug/global.md"
        assert debug_wf.prompts.lifecycle_prompt == "prompts/debug/lifecycle.md"

    def test_parse_legacy_single_workflow(self, tmp_path):
        """Should parse legacy config without workflows section."""
        yaml_content = """
tracker:
  project_slug: test-project

states:
  reproduce:
    type: agent
    prompt: prompts/reproduce.md
"""
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text(yaml_content)

        result = parse_workflow_file(workflow_file)

        # Should have empty workflows dict
        assert result.config.workflows == {}
        # Root states should still be populated
        assert "reproduce" in result.config.states


class TestWorkflowEntryState:
    """Tests for entry state resolution per workflow."""

    def test_entry_state_for_workflow(self):
        """Should return first agent state for a workflow."""
        wf = WorkflowConfig(
            name="debug",
            states={
                "reproduce": StateConfig(name="reproduce", type="agent"),
                "fix": StateConfig(name="fix", type="agent"),
            },
        )

        cfg = ServiceConfig()
        entry = cfg.entry_state_for_workflow(wf)

        assert entry == "reproduce"

    def test_entry_state_no_agent_states(self):
        """Should return None when workflow has no agent states."""
        wf = WorkflowConfig(
            name="empty",
            states={
                "terminal": StateConfig(name="terminal", type="terminal"),
            },
        )

        cfg = ServiceConfig()
        entry = cfg.entry_state_for_workflow(wf)

        assert entry is None


class TestGetDefaultWorkflowName:
    """Tests for default workflow name resolution."""

    def test_get_default_workflow_name(self):
        """Should return name of default workflow."""
        cfg = ServiceConfig()
        cfg.workflows = {
            "debug": WorkflowConfig(name="debug", label="debug", states={}),
            "default": WorkflowConfig(name="default", default=True, states={}),
        }

        result = cfg.get_default_workflow_name()

        assert result == "default"

    def test_get_default_workflow_name_no_default(self):
        """Should return None when no default workflow exists."""
        cfg = ServiceConfig()
        cfg.workflows = {
            "debug": WorkflowConfig(name="debug", label="debug", states={}),
        }

        result = cfg.get_default_workflow_name()

        assert result is None

    def test_get_default_workflow_name_legacy_mode(self):
        """Should return 'default' in legacy mode."""
        cfg = ServiceConfig()
        cfg.states = {"reproduce": StateConfig()}
        # No workflows section

        result = cfg.get_default_workflow_name()

        assert result == "default"
