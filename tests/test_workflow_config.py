"""Tests for multi-workflow configuration support."""

import pytest
from dataclasses import dataclass
from typing import Any

from stokowski.config import (
    ServiceConfig,
    WorkflowConfig,
    StateConfig,
    PromptsConfig,
    parse_workflow_file,
    validate_config,
)
from stokowski.models import Issue


@dataclass
class MockIssue:
    """Mock issue for testing."""
    id: str = "issue-1"
    identifier: str = "TEST-1"
    title: str = "Test Issue"
    labels: list[str] = None

    def __post_init__(self):
        if self.labels is None:
            self.labels = []


class TestWorkflowConfig:
    """Tests for WorkflowConfig dataclass."""

    def test_workflow_config_creation(self):
        """Should create WorkflowConfig with all fields."""
        states = {
            "reproduce": StateConfig(name="reproduce", type="agent"),
            "fix": StateConfig(name="fix", type="agent"),
        }
        prompts = PromptsConfig(global_prompt="prompts/debug/global.md")

        wf = WorkflowConfig(
            name="debug",
            label="debug",
            default=False,
            states=states,
            prompts=prompts,
        )

        assert wf.name == "debug"
        assert wf.label == "debug"
        assert wf.default is False
        assert len(wf.states) == 2
        assert wf.prompts.global_prompt == "prompts/debug/global.md"

    def test_workflow_config_defaults(self):
        """Should create WorkflowConfig with default values."""
        wf = WorkflowConfig()

        assert wf.name == ""
        assert wf.label is None
        assert wf.default is False
        assert wf.states == {}
        assert isinstance(wf.prompts, PromptsConfig)


class TestGetWorkflowForIssue:
    """Tests for ServiceConfig.get_workflow_for_issue()."""

    def test_route_by_label_match(self):
        """Should route issue to workflow based on label match."""
        debug_wf = WorkflowConfig(name="debug", label="debug", states={"reproduce": StateConfig()})
        feature_wf = WorkflowConfig(name="feature", label="feature", states={"spec": StateConfig()})

        cfg = ServiceConfig()
        cfg.workflows = {
            "debug": debug_wf,
            "feature": feature_wf,
        }

        issue = MockIssue(labels=["debug"])
        result = cfg.get_workflow_for_issue(issue)

        assert result.name == "debug"

    def test_route_by_first_match(self):
        """Should use first matching workflow when multiple labels match."""
        debug_wf = WorkflowConfig(name="debug", label="debug", states={})
        feature_wf = WorkflowConfig(name="feature", label="feature", states={})

        cfg = ServiceConfig()
        cfg.workflows = {
            "debug": debug_wf,
            "feature": feature_wf,
        }

        # Both labels present - first in YAML order wins
        issue = MockIssue(labels=["feature", "debug"])
        result = cfg.get_workflow_for_issue(issue)

        assert result.name == "debug"  # First in workflows dict

    def test_fallback_to_default(self):
        """Should fallback to default workflow when no label matches."""
        debug_wf = WorkflowConfig(name="debug", label="debug", states={})
        default_wf = WorkflowConfig(name="default", default=True, states={})

        cfg = ServiceConfig()
        cfg.workflows = {
            "debug": debug_wf,
            "default": default_wf,
        }

        issue = MockIssue(labels=["unknown-label"])
        result = cfg.get_workflow_for_issue(issue)

        assert result.name == "default"

    def test_error_when_no_match_and_no_default(self):
        """Should raise ValueError when no workflow matches and no default."""
        debug_wf = WorkflowConfig(name="debug", label="debug", states={})

        cfg = ServiceConfig()
        cfg.workflows = {
            "debug": debug_wf,
        }

        issue = MockIssue(labels=["unknown-label"])

        with pytest.raises(ValueError, match="No workflow matches issue labels"):
            cfg.get_workflow_for_issue(issue)

    def test_legacy_mode_single_workflow(self):
        """Should create implicit default workflow in legacy mode."""
        cfg = ServiceConfig()
        cfg.states = {"reproduce": StateConfig(name="reproduce", type="agent")}
        cfg.prompts = PromptsConfig(global_prompt="prompts/global.md")
        # No workflows section

        issue = MockIssue(labels=["anything"])
        result = cfg.get_workflow_for_issue(issue)

        assert result.name == "default"
        assert result.default is True
        assert len(result.states) == 1


class TestParseWorkflowFile:
    """Tests for parsing multi-workflow configuration."""

    def test_parse_multi_workflow_yaml(self, tmp_path):
        """Should parse workflows section from YAML."""
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
      fix:
        type: agent
        transitions:
          success: terminal
    prompts:
      global_prompt: prompts/debug/global.md

  feature:
    label: feature
    default: true
    states:
      spec:
        type: agent
        transitions:
          success: build
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
        assert "fix" in debug_wf.states

        feature_wf = result.config.workflows["feature"]
        assert feature_wf.label == "feature"
        assert feature_wf.default is True
        assert "spec" in feature_wf.states

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

        assert result.config.workflows == {}
        assert "reproduce" in result.config.states

    def test_workflow_prompts_override(self, tmp_path):
        """Should parse workflow-scoped prompts."""
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


class TestDuplicateLabelValidation:
    """Tests for duplicate workflow label validation."""

    def test_duplicate_labels_detected(self):
        """Should report error when two workflows have the same label."""
        wf1 = WorkflowConfig(
            name="debug",
            label="shared-label",
            states={"reproduce": StateConfig(name="reproduce", type="agent")},
        )
        wf2 = WorkflowConfig(
            name="feature",
            label="shared-label",
            states={"spec": StateConfig(name="spec", type="agent")},
        )

        cfg = ServiceConfig()
        cfg.workflows = {
            "debug": wf1,
            "feature": wf2,
        }

        errors = validate_config(cfg)

        expected = "Multiple workflows have the same label 'shared-label': debug, feature"
        assert expected in errors

    def test_workflows_without_labels_no_error(self):
        """Should not report error for workflows without labels (labels are optional)."""
        wf1 = WorkflowConfig(
            name="workflow1",
            label=None,
            states={"reproduce": StateConfig(name="reproduce", type="agent")},
        )
        wf2 = WorkflowConfig(
            name="workflow2",
            label=None,
            states={"spec": StateConfig(name="spec", type="agent")},
        )

        cfg = ServiceConfig()
        cfg.workflows = {
            "workflow1": wf1,
            "workflow2": wf2,
        }

        # Filter to only label-related errors
        errors = [e for e in validate_config(cfg) if "label" in e.lower()]

        assert len(errors) == 0

    def test_different_labels_no_error(self):
        """Should not report error when workflows have different labels."""
        wf1 = WorkflowConfig(
            name="debug",
            label="debug-label",
            states={"reproduce": StateConfig(name="reproduce", type="agent")},
        )
        wf2 = WorkflowConfig(
            name="feature",
            label="feature-label",
            states={"spec": StateConfig(name="spec", type="agent")},
        )

        cfg = ServiceConfig()
        cfg.workflows = {
            "debug": wf1,
            "feature": wf2,
        }

        errors = validate_config(cfg)

        # Filter to only label-related errors
        label_errors = [e for e in errors if "label" in e.lower()]

        assert len(label_errors) == 0

    def test_empty_string_labels_not_duplicate(self):
        """Empty string labels should not be considered duplicates."""
        cfg = ServiceConfig()
        cfg.workflows = {
            "wf1": WorkflowConfig(label="", name="wf1", states={"s1": StateConfig(name="s1", type="agent")}),
            "wf2": WorkflowConfig(label="", name="wf2", states={"s2": StateConfig(name="s2", type="agent")}),
        }
        errors = validate_config(cfg)
        # Empty labels should be skipped, not considered duplicates
        label_errors = [e for e in errors if "label" in e.lower()]
        assert len(label_errors) == 0, f"Empty labels should not produce duplicates: {label_errors}"
