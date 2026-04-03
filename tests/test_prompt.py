"""Tests for prompt assembly module."""

import pytest

from stokowski.config import LinearStatesConfig, PromptsConfig, ServiceConfig, StateConfig
from stokowski.models import Issue
from stokowski.prompt import (
    assemble_prompt,
    build_lifecycle_context,
    build_lifecycle_section,
    load_prompt_file,
    render_template,
)


class TestBuildLifecycleSection:
    """Tests for build_lifecycle_section with externalized template."""

    def test_renders_template_with_variables(self):
        """Template variables are substituted correctly."""
        issue = Issue(
            id="test-123",
            identifier="PROJ-1",
            title="Test issue",
            state="In Progress",
        )
        template = "Issue: {{ issue.identifier }} - {{ issue.title }}"

        result = build_lifecycle_section(
            lifecycle_template=template,
            issue=issue,
            state_name="implement",
            state_cfg=StateConfig(name="implement", type="agent"),
            linear_states=LinearStatesConfig(),
        )

        assert "Issue: PROJ-1 - Test issue" in result

    def test_renders_gate_section_when_has_gate_transition(self):
        """Gate section rendered when template checks has_gate_transition."""
        issue = Issue(
            id="test-123",
            identifier="PROJ-1",
            title="Test issue",
            state="In Progress",
        )
        template = "{% if has_gate_transition %}GATE REQUIRED{% endif %}"

        workflow_states = {
            "implement": StateConfig(name="implement", type="agent"),
            "review": StateConfig(name="review", type="gate"),
        }
        state_cfg = StateConfig(
            name="implement",
            type="agent",
            transitions={"complete": "review"},
        )

        result = build_lifecycle_section(
            lifecycle_template=template,
            issue=issue,
            state_name="implement",
            state_cfg=state_cfg,
            linear_states=LinearStatesConfig(),
            workflow_states=workflow_states,
        )

        assert "GATE REQUIRED" in result

    def test_renders_previous_error_when_provided(self):
        """Previous error is available in template context."""
        issue = Issue(
            id="test-123",
            identifier="PROJ-1",
            title="Test issue",
            state="In Progress",
        )
        template = "{% if previous_error %}Error: {{ previous_error }}{% endif %}"

        result = build_lifecycle_section(
            lifecycle_template=template,
            issue=issue,
            state_name="implement",
            state_cfg=StateConfig(name="implement", type="agent"),
            linear_states=LinearStatesConfig(),
            previous_error="Something failed",
        )

        assert "Error: Something failed" in result

    def test_renders_rework_info_when_is_rework(self):
        """Rework information available in template context."""
        issue = Issue(
            id="test-123",
            identifier="PROJ-1",
            title="Test issue",
            state="In Progress",
        )
        template = "{% if is_rework %}REWORK MODE{% endif %}"

        result = build_lifecycle_section(
            lifecycle_template=template,
            issue=issue,
            state_name="implement",
            state_cfg=StateConfig(name="implement", type="agent"),
            linear_states=LinearStatesConfig(),
            is_rework=True,
        )

        assert "REWORK MODE" in result

    def test_renders_transitions(self):
        """Transitions available in template context."""
        issue = Issue(
            id="test-123",
            identifier="PROJ-1",
            title="Test issue",
            state="In Progress",
        )
        template = (
            "{% for trigger, target in transitions.items() %}{{ trigger }}:{{ target }}{% endfor %}"
        )
        state_cfg = StateConfig(
            name="implement",
            type="agent",
            transitions={"complete": "review", "fail": "rework"},
        )

        result = build_lifecycle_section(
            lifecycle_template=template,
            issue=issue,
            state_name="implement",
            state_cfg=state_cfg,
            linear_states=LinearStatesConfig(),
        )

        assert "complete:review" in result
        assert "fail:rework" in result

    def test_renders_recent_comments(self):
        """Recent comments available in template context."""
        issue = Issue(
            id="test-123",
            identifier="PROJ-1",
            title="Test issue",
            state="In Progress",
        )
        template = "{% for comment in recent_comments %}{{ comment.body }}{% endfor %}"

        result = build_lifecycle_section(
            lifecycle_template=template,
            issue=issue,
            state_name="implement",
            state_cfg=StateConfig(name="implement", type="agent"),
            linear_states=LinearStatesConfig(),
            recent_comments=[
                {"body": "Fix this", "createdAt": "2024-01-01"},
                {"body": "And that", "createdAt": "2024-01-02"},
            ],
        )

        assert "Fix this" in result
        assert "And that" in result


class TestLifecycleContext:
    """Tests for build_lifecycle_context."""

    def test_includes_all_required_variables(self):
        """Context contains all template variables."""
        issue = Issue(
            id="test-123",
            identifier="PROJ-1",
            title="Test issue",
            state="In Progress",
        )

        context = build_lifecycle_context(
            issue=issue,
            state_name="implement",
            state_cfg=StateConfig(name="implement", type="agent"),
            linear_states=LinearStatesConfig(),
            run=5,
            is_rework=True,
            previous_error="error message",
            recent_comments=[{"body": "comment"}],
        )

        assert context["issue"] == issue
        assert context["state_name"] == "implement"
        assert context["run"] == 5
        assert context["is_rework"] is True
        assert context["previous_error"] == "error message"
        assert context["recent_comments"] == [{"body": "comment"}]
        assert "transitions" in context
        assert "has_gate_transition" in context
        assert "gate_targets" in context


class TestRenderTemplate:
    """Tests for render_template function."""

    def test_renders_jinja2_template(self):
        """Basic Jinja2 rendering works."""
        template = "Hello {{ name }}!"
        context = {"name": "World"}

        result = render_template(template, context)

        assert result == "Hello World!"

    def test_missing_variables_render_empty(self):
        """Missing variables render as empty string (no error)."""
        template = "Hello {{ missing }}!"
        context = {}

        result = render_template(template, context)

        assert result == "Hello !"


class TestLoadPromptFile:
    """Tests for load_prompt_file function."""

    def test_loads_file_from_relative_path(self, tmp_path):
        """Loads file relative to workflow directory."""
        workflow_dir = tmp_path / "workflow"
        workflow_dir.mkdir()
        prompt_file = workflow_dir / "prompts" / "test.md"
        prompt_file.parent.mkdir()
        prompt_file.write_text("Test content")

        result = load_prompt_file("prompts/test.md", workflow_dir)

        assert result == "Test content"

    def test_loads_file_from_absolute_path(self, tmp_path):
        """Loads file from absolute path."""
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("Absolute content")

        result = load_prompt_file(str(prompt_file), "/any/workflow/dir")

        assert result == "Absolute content"

    def test_raises_file_not_found_when_missing(self, tmp_path):
        """Raises FileNotFoundError when file doesn't exist."""
        with pytest.raises(FileNotFoundError) as exc_info:
            load_prompt_file("missing.md", tmp_path)

        assert "missing.md" in str(exc_info.value)


class TestAssemblePrompt:
    """Tests for assemble_prompt function."""

    def test_loads_lifecycle_template_from_config(self, tmp_path):
        """Lifecycle template loaded from configured path."""
        # Create workflow directory with lifecycle template
        workflow_dir = tmp_path / "workflow"
        workflow_dir.mkdir()
        lifecycle_file = workflow_dir / "prompts" / "lifecycle.md"
        lifecycle_file.parent.mkdir()
        lifecycle_file.write_text("LIFECYCLE: {{ issue.identifier }}")

        cfg = ServiceConfig(prompts=PromptsConfig(lifecycle_prompt="prompts/lifecycle.md"))
        issue = Issue(
            id="test-123",
            identifier="PROJ-1",
            title="Test issue",
            state="In Progress",
        )
        state_cfg = StateConfig(
            name="implement",
            type="agent",
            prompt="prompts/stage.md",
        )
        stage_file = workflow_dir / "prompts" / "stage.md"
        stage_file.write_text("Stage content")

        result = assemble_prompt(
            cfg=cfg,
            workflow_dir=str(workflow_dir),
            issue=issue,
            state_name="implement",
            state_cfg=state_cfg,
            workflow_states={},
        )

        assert "LIFECYCLE: PROJ-1" in result

    def test_uses_default_lifecycle_path_when_not_configured(self, tmp_path):
        """Default lifecycle path used when not explicitly configured."""
        workflow_dir = tmp_path / "workflow"
        workflow_dir.mkdir()
        lifecycle_file = workflow_dir / "prompts" / "lifecycle.md"
        lifecycle_file.parent.mkdir()
        lifecycle_file.write_text("DEFAULT LIFECYCLE")

        cfg = ServiceConfig()  # Uses default lifecycle_prompt
        issue = Issue(
            id="test-123",
            identifier="PROJ-1",
            title="Test issue",
            state="In Progress",
        )
        state_cfg = StateConfig(name="implement", type="agent")

        result = assemble_prompt(
            cfg=cfg,
            workflow_dir=str(workflow_dir),
            issue=issue,
            state_name="implement",
            state_cfg=state_cfg,
            workflow_states={},
        )

        assert "DEFAULT LIFECYCLE" in result

    def test_raises_when_lifecycle_file_missing(self, tmp_path):
        """FileNotFoundError when lifecycle template is missing."""
        cfg = ServiceConfig(prompts=PromptsConfig(lifecycle_prompt="prompts/missing.md"))
        issue = Issue(
            id="test-123",
            identifier="PROJ-1",
            title="Test issue",
            state="In Progress",
        )
        state_cfg = StateConfig(name="implement", type="agent")

        with pytest.raises(FileNotFoundError):
            assemble_prompt(
                cfg=cfg,
                workflow_dir=str(tmp_path),
                issue=issue,
                state_name="implement",
                state_cfg=state_cfg,
                workflow_states={},
            )
