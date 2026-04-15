"""Three-layer prompt assembly for state machine workflows.

Assembles prompts from:
1. Global prompt — loaded from a .md file referenced in config
2. Stage prompt — loaded from the state's prompt .md file
3. Lifecycle injection — auto-generated from config + Linear data
"""

from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path
from typing import Any

from jinja2 import BaseLoader, Environment, Undefined, select_autoescape

from .config import LinearStatesConfig, PromptsConfig, ServiceConfig, StateConfig
from .models import Issue
from .tracking import (
    get_comments_since,
    get_last_gate_waiting_timestamp,
    get_last_tracking_timestamp,
)

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
    empty strings rather than raising errors. Autoescape is enabled
    for security (templates render prompts, not HTML).
    """
    env = Environment(
        loader=BaseLoader(),
        undefined=_SilentUndefined,
        autoescape=select_autoescape(),
    )
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
    is_rework: bool = False,
) -> dict[str, Any]:
    """Build the Jinja2 template context dict from issue and run metadata.

    Args:
        issue: The Linear issue being worked on.
        state_name: Internal state machine state name.
        run: Current run number for this state.
        attempt: Retry attempt within this run.
        last_run_at: ISO timestamp of the last run, if any.
        is_rework: Whether this is a rework run.

    Returns:
        A dict with the issue object and run metadata for Jinja2 rendering.
    """
    return {
        "issue": issue,
        "state_name": state_name,
        "run": run,
        "attempt": attempt,
        "last_run_at": last_run_at or "",
        "is_rework": is_rework,
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
    include_images: bool = True,
) -> dict[str, Any]:
    """Build the extended template context with lifecycle-specific variables.

    Extends the base template context with lifecycle-specific variables.

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
        include_images: Whether to include image references in context.

    Returns:
        Dict with all lifecycle-specific template variables.
    """
    # Start with base context
    context = build_template_context(issue=issue, state_name=state_name, run=run)

    # Check if any transition leads to a gate
    has_gate_transition = False
    gate_targets = []
    if workflow_states and state_cfg.transitions:
        for trigger, target in state_cfg.transitions.items():
            target_cfg = workflow_states.get(target)
            if target_cfg and getattr(target_cfg, "type", None) == "gate":
                has_gate_transition = True
                gate_targets.append((trigger, target))

    # Build image references if requested
    has_images = False
    image_references: list[dict[str, str]] = []
    if include_images and recent_comments:
        has_images = any(c.get("downloaded_images") for c in recent_comments)
        image_references = build_image_references(recent_comments)

    # Add lifecycle-specific variables
    context.update(
        {
            "previous_error": previous_error or "",
            "is_rework": is_rework,
            "recent_comments": recent_comments or [],
            "transitions": state_cfg.transitions or {},
            "has_gate_transition": has_gate_transition,
            "gate_targets": gate_targets,
            "is_agent_gate": state_cfg.type == "agent-gate",
            "agent_gate_default_transition": (
                (state_cfg.default_transition or "") if state_cfg.type == "agent-gate" else ""
            ),
            "has_images": has_images,
            "image_references": image_references,
        }
    )

    return context


async def build_lifecycle_section(
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
    embed_images: bool = True,
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
        embed_images: Whether to embed images as base64 in the output.

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

    # Render the lifecycle template
    rendered = render_template(lifecycle_template, context)

    # Embed images if requested and present
    if embed_images and recent_comments and context.get("has_images"):
        image_section = await embed_images_in_prompt(recent_comments)
        if image_section:
            rendered = rendered + "\n\n" + image_section

    return rendered


async def assemble_prompt(
    cfg: ServiceConfig,
    workflow_dir: str | Path,
    issue: Issue,
    state_name: str,
    state_cfg: StateConfig,
    workflow_states: dict[str, Any],
    workflow_prompts: PromptsConfig | None = None,
    run: int = 1,
    is_rework: bool = False,
    is_resumed_session: bool = False,
    include_stage_prompt_on_resume: bool = False,
    attempt: int = 1,
    last_run_at: str | None = None,
    comments: list[dict[str, Any]] | None = None,
    previous_error: str | None = None,
) -> str:
    """Orchestrate three-layer prompt assembly.

    Combines:
    1. Global prompt (from workflow or config's prompts.global_prompt path)
    2. Stage prompt (from state_cfg.prompt path)
    3. Lifecycle injection (auto-generated)

    Each layer is rendered as a Jinja2 template with the issue context.

    Args:
        cfg: The full service config.
        workflow_dir: Directory containing the workflow file.
        issue: The Linear issue.
        state_name: Internal state machine state name.
        state_cfg: Configuration for the current state.
        workflow_states: All states in the current workflow.
        workflow_prompts: PromptsConfig for the current workflow (optional, falls back to cfg.prompts).
        run: Current run number.
        is_rework: Whether this is a rework run.
        is_resumed_session: Whether the current turn resumes an existing session.
        include_stage_prompt_on_resume: Whether stage prompt should be injected
            for resumed turns (used when entering a new stage in a resumed session).
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
        is_rework=is_rework,
    )

    parts: list[str] = []

    # Use workflow-specific prompts if provided, otherwise fall back to global config
    prompts = workflow_prompts if workflow_prompts is not None else cfg.prompts

    include_static_prompts = not is_resumed_session

    # Layer 1: Global prompt
    if prompts.global_prompt and include_static_prompts:
        try:
            raw = load_prompt_file(prompts.global_prompt, workflow_dir)
            rendered = render_template(raw, context)
            parts.append(rendered)
        except FileNotFoundError:
            log.warning("Global prompt file not found: %s", prompts.global_prompt)
    elif prompts.global_prompt:
        log.info("Skipped global prompt for '%s' due to resumed session", state_name)

    stage_mode = "non-rework"
    include_stage_prompt = include_static_prompts or include_stage_prompt_on_resume
    if is_rework and is_resumed_session:
        stage_mode = "rework-resume"
    elif is_rework:
        stage_mode = "rework-fresh"
    elif is_resumed_session:
        stage_mode = (
            "non-rework-resume-new-stage" if include_stage_prompt_on_resume else "non-rework-resume"
        )

    # Layer 2: Stage prompt
    if state_cfg.prompt and include_stage_prompt:
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
    elif state_cfg.prompt:
        log.info("Skipped stage prompt for '%s' due to prompt mode: %s", state_name, stage_mode)

    # Layer 3: Lifecycle injection
    # Filter comments to recent non-tracking ones
    recent: list[dict[str, Any]] = []
    if comments:
        # Prefer comments since the latest waiting gate so rework runs include
        # reviewer feedback left during gate review.
        last_ts = get_last_gate_waiting_timestamp(comments) or get_last_tracking_timestamp(comments)
        recent = get_comments_since(comments, last_ts)

    # Load lifecycle template (required)
    lifecycle_template = load_prompt_file(prompts.lifecycle_prompt, workflow_dir)

    lifecycle = await build_lifecycle_section(
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


def _get_mime_type_from_path(path: Path) -> str:
    """Determine MIME type from file extension."""
    ext = path.suffix.lower()
    mime_types: dict[str, str] = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".heic": "image/heic",
        ".heif": "image/heic",
    }
    return mime_types.get(ext, "image/png")


async def embed_images_in_prompt(
    comments: list[dict[str, Any]],
    max_images_per_comment: int = 5,
    max_total_images: int = 20,
) -> str:
    """Generate markdown with embedded base64 images from comment attachments.

    Args:
        comments: List of comment nodes with 'downloaded_images' key containing
            list of dicts with 'path', 'title', 'mime_type'.
        max_images_per_comment: Maximum images to embed per comment.
        max_total_images: Maximum total images across all comments.

    Returns:
        Markdown string with embedded base64 images.
    """
    image_markdown: list[str] = []
    total_count = 0

    for comment in comments:
        images = comment.get("downloaded_images", [])
        if not images:
            continue

        for img_info in images[:max_images_per_comment]:
            if total_count >= max_total_images:
                log.debug("Reached max_total_images limit (%d)", max_total_images)
                break

            img_path_str = img_info.get("path")
            if not img_path_str:
                continue

            path = Path(img_path_str)
            if not path.exists():
                log.warning("Image file not found: %s", img_path_str)
                continue

            try:
                # Read and encode using async thread to avoid blocking
                data = await asyncio.to_thread(path.read_bytes)
                mime_type = img_info.get("mime_type") or _get_mime_type_from_path(path)
                b64 = base64.b64encode(data).decode("ascii")

                title = img_info.get("title", path.name)

                # Add markdown image with data URI
                image_markdown.append(f"![{title}](data:{mime_type};base64,{b64})")
                total_count += 1
            except Exception as e:
                log.warning("Failed to embed image %s: %s", img_path_str, e)
                continue

    return "\n\n".join(image_markdown)


def build_image_references(comments: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Build image references for template context.

    Args:
        comments: List of comment nodes with 'downloaded_images'.

    Returns:
        List of image reference dicts with 'path', 'title', 'comment_id'.
    """
    references: list[dict[str, str]] = []
    for comment in comments:
        comment_id = comment.get("id", "")
        images = comment.get("downloaded_images", [])
        for img_info in images:
            references.append(
                {
                    "path": img_info.get("path", ""),
                    "title": img_info.get("title", ""),
                    "comment_id": comment_id,
                }
            )
    return references
