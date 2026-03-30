"""Three-layer prompt assembly for state machine workflows.

Assembles prompts from:
1. Global prompt — loaded from a .md file referenced in config
2. Stage prompt — loaded from the state's prompt .md file
3. Lifecycle injection — auto-generated from config + Linear data
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jinja2 import BaseLoader, Environment, Undefined

from .config import LinearStatesConfig, ServiceConfig, StateConfig
from .models import Issue
from .tracking import get_comments_since, get_last_tracking_timestamp

log = logging.getLogger(__name__)


def load_prompt_file(path: str, workflow_dir: str | Path) -> str:
    """Load a .md prompt file relative to the workflow directory.

    Args:
        path: File path (absolute or relative to workflow_dir).
        workflow_dir: Directory containing the workflow file.

    Returns:
        The file contents as a string.

    Raises:
        FileNotFoundError: If the resolved path does not exist.
    """
    p = Path(path)
    if not p.is_absolute():
        p = Path(workflow_dir) / p
    p = p.resolve()
    if not p.exists():
        raise FileNotFoundError(f"Prompt file not found: {p}")
    return p.read_text()


def render_template(template_str: str, context: dict[str, Any]) -> str:
    """Render a Jinja2 template string with the given context.

    Uses a permissive undefined handler so missing variables render as
    empty strings rather than raising errors.
    """
    env = Environment(loader=BaseLoader(), undefined=_SilentUndefined)
    template = env.from_string(template_str)
    return template.render(**context)


class _SilentUndefined(Undefined):
    """Jinja2 undefined that renders as empty string instead of raising."""

    def __str__(self) -> str:
        return ""

    def __iter__(self) -> Any:
        return iter([])

    def __bool__(self) -> bool:
        return False

    def _fail_with_undefined_error(self, *args: Any, **kwargs: Any) -> Any:
        return _SilentUndefined()

    def __getattr__(self, name: str) -> _SilentUndefined:
        if name.startswith("_"):
            raise AttributeError(name)
        return _SilentUndefined()

    def __getitem__(self, name: str) -> _SilentUndefined:
        return _SilentUndefined()


def build_template_context(
    issue: Issue,
    state_name: str,
    run: int = 1,
    attempt: int = 1,
    last_run_at: str | None = None,
) -> dict[str, Any]:
    """Build the Jinja2 template context dict from issue and run metadata.

    Args:
        issue: The Linear issue being worked on.
        state_name: Internal state machine state name.
        run: Current run number for this state.
        attempt: Retry attempt within this run.
        last_run_at: ISO timestamp of the last run, if any.

    Returns:
        A flat dict suitable for Jinja2 rendering.
    """
    return {
        "issue_id": issue.id,
        "issue_identifier": issue.identifier,
        "issue_title": issue.title,
        "issue_description": issue.description or "",
        "issue_url": issue.url or "",
        "issue_priority": issue.priority,
        "issue_state": issue.state,
        "issue_branch": issue.branch_name or "",
        "issue_labels": issue.labels,
        "state_name": state_name,
        "run": run,
        "attempt": attempt,
        "last_run_at": last_run_at or "",
    }


def build_lifecycle_context(
    issue: Issue,
    state_name: str,
    state_cfg: StateConfig,
    linear_states: LinearStatesConfig,
    workflow_states: dict[str, Any] | None = None,
    run: int = 1,
    is_rework: bool = False,
    recent_comments: list[dict[str, Any]] | None = None,
    previous_error: str | None = None,
) -> dict[str, Any]:
    """Build the extended template context with lifecycle-specific variables.

    Args:
        issue: The Linear issue.
        state_name: Internal state machine state name.
        state_cfg: Configuration for the current state.
        linear_states: Linear state name mappings.
        workflow_states: All workflow states for gate detection.
        run: Current run number.
        is_rework: Whether this is a rework run after gate rejection.
        recent_comments: Non-tracking comments since last run.
        previous_error: Error message from the previous failed attempt.

    Returns:
        Dict with all lifecycle-specific template variables.
    """
    # Check if any transition leads to a gate
    has_gate_transition = False
    gate_targets = []
    if workflow_states and state_cfg.transitions:
        for trigger, target in state_cfg.transitions.items():
            target_cfg = workflow_states.get(target)
            if target_cfg and getattr(target_cfg, "type", None) == "gate":
                has_gate_transition = True
                gate_targets.append((trigger, target))

    return {
        "previous_error": previous_error or "",
        "is_rework": is_rework,
        "recent_comments": recent_comments or [],
        "transitions": state_cfg.transitions or {},
        "has_gate_transition": has_gate_transition,
        "gate_targets": gate_targets,
        "issue": issue,
        "state_name": state_name,
        "run": run,
    }


def build_lifecycle_section(
    lifecycle_template: str,
    issue: Issue,
    state_name: str,
    state_cfg: StateConfig,
    linear_states: LinearStatesConfig,
    workflow_states: dict[str, Any] | None = None,
    run: int = 1,
    is_rework: bool = False,
    recent_comments: list[dict[str, Any]] | None = None,
    previous_error: str | None = None,
) -> str:
    """Render the lifecycle section from an external template.

    Loads and renders the lifecycle template with context variables.
    All content comes from the external template file - no hardcoded strings.

    Args:
        lifecycle_template: The lifecycle template content to render.
        issue: The Linear issue.
        state_name: Internal state machine state name.
        state_cfg: Configuration for the current state.
        linear_states: Linear state name mappings.
        workflow_states: All workflow states for gate detection.
        run: Current run number.
        is_rework: Whether this is a rework run after gate rejection.
        recent_comments: Non-tracking comments since last run.
        previous_error: Error message from the previous failed attempt.

    Returns:
        The rendered lifecycle section as a markdown string.
    """
    context = build_lifecycle_context(
        issue=issue,
        state_name=state_name,
        state_cfg=state_cfg,
        linear_states=linear_states,
        workflow_states=workflow_states,
        run=run,
        is_rework=is_rework,
        recent_comments=recent_comments,
        previous_error=previous_error,
    )
    return render_template(lifecycle_template, context)


def assemble_prompt(
    cfg: ServiceConfig,
    workflow_dir: str | Path,
    issue: Issue,
    state_name: str,
    state_cfg: StateConfig,
    workflow_states: dict[str, Any],
    run: int = 1,
    is_rework: bool = False,
    attempt: int = 1,
    last_run_at: str | None = None,
    comments: list[dict[str, Any]] | None = None,
    previous_error: str | None = None,
) -> str:
    """Orchestrate three-layer prompt assembly.

    Combines:
    1. Global prompt (from config's prompts.global_prompt path)
    2. Stage prompt (from state_cfg.prompt path)
    3. Lifecycle injection (auto-generated)

    Each layer is rendered as a Jinja2 template with the issue context.

    Args:
        cfg: The full service config.
        workflow_dir: Directory containing the workflow file.
        issue: The Linear issue.
        state_name: Internal state machine state name.
        state_cfg: Configuration for the current state.
        run: Current run number.
        is_rework: Whether this is a rework run.
        attempt: Retry attempt within this run.
        last_run_at: ISO timestamp of the last run.
        comments: All comments on the issue (for filtering).
        previous_error: Error from previous attempt for retry feedback.

    Returns:
        The fully assembled prompt string.
    """
    context = build_template_context(
        issue=issue,
        state_name=state_name,
        run=run,
        attempt=attempt,
        last_run_at=last_run_at,
    )

    parts: list[str] = []

    # Layer 1: Global prompt
    if cfg.prompts.global_prompt:
        try:
            raw = load_prompt_file(cfg.prompts.global_prompt, workflow_dir)
            rendered = render_template(raw, context)
            parts.append(rendered)
        except FileNotFoundError:
            log.warning(
                "Global prompt file not found: %s", cfg.prompts.global_prompt
            )

    # Layer 2: Stage prompt
    if state_cfg.prompt:
        try:
            raw = load_prompt_file(state_cfg.prompt, workflow_dir)
            rendered = render_template(raw, context)
            parts.append(rendered)
            log.info(f"Loaded stage prompt for '{state_name}': {state_cfg.prompt}")
        except FileNotFoundError:
            log.warning(
                "Stage prompt file not found for state '%s': %s",
                state_name,
                state_cfg.prompt,
            )

    # Layer 3: Lifecycle injection
    # Filter comments to recent non-tracking ones
    recent: list[dict[str, Any]] = []
    if comments:
        last_ts = get_last_tracking_timestamp(comments)
        recent = get_comments_since(comments, last_ts)

    # Load lifecycle template (required)
    lifecycle_template = load_prompt_file(cfg.prompts.lifecycle_prompt, workflow_dir)

    lifecycle = build_lifecycle_section(
        lifecycle_template=lifecycle_template,
        issue=issue,
        state_name=state_name,
        state_cfg=state_cfg,
        linear_states=cfg.linear_states,
        workflow_states=workflow_states,
        run=run,
        is_rework=is_rework,
        recent_comments=recent,
        previous_error=previous_error,
    )
    parts.append(lifecycle)

    return "\n\n".join(parts)
