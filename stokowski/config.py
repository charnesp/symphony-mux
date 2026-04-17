"""Workflow loader and typed configuration."""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)


@dataclass
class TrackerConnectionConfig:
    """Configuration for connecting to a tracker backend.

    This is a generic configuration that can be used with any
    tracker implementation (Linear, GitHub Issues, etc.).
    """

    kind: str = "linear"
    endpoint: str = "https://api.linear.app/graphql"
    api_key: str = ""
    project_slug: str = ""

    # Additional tracker-specific configuration options
    # These are passed through to the tracker client
    extra: dict[str, Any] = field(default_factory=lambda: {})


# Backwards-compatible alias for code that imports TrackerConfig
TrackerConfig = TrackerConnectionConfig


@dataclass
class PollingConfig:
    interval_ms: int = 30_000


@dataclass
class WorkspaceConfig:
    root: str = ""

    def resolved_root(self) -> Path:
        if self.root:
            return Path(os.path.expandvars(os.path.expanduser(self.root)))
        return Path(tempfile.gettempdir()) / "stokowski_workspaces"


@dataclass
class HooksConfig:
    after_create: str | None = None
    before_run: str | None = None
    after_run: str | None = None
    before_remove: str | None = None
    on_stage_enter: str | None = None
    timeout_ms: int = 60_000


@dataclass
class ClaudeConfig:
    command: str = "claude"
    permission_mode: str = "auto"  # "auto" or "allowedTools"
    allowed_tools: list[str] = field(
        default_factory=lambda: ["Bash", "Read", "Edit", "Write", "Glob", "Grep"]
    )
    model: str | None = None
    max_turns: int = 20  # Parsed/merged from YAML; not used to cap orchestrator dispatches.
    turn_timeout_ms: int = 3_600_000
    stall_timeout_ms: int = 300_000
    append_system_prompt: str | None = None


@dataclass
class AgentConfig:
    max_concurrent_agents: int = 5
    max_retry_backoff_ms: int = 300_000
    max_concurrent_agents_by_state: dict[str, int] = field(default_factory=lambda: {})


@dataclass
class ServerConfig:
    port: int | None = None


@dataclass
class LinearStatesConfig:
    """Maps logical state names to actual Linear state names."""

    todo: str = "Todo"
    active: str = "In Progress"
    review: str = "Human Review"
    gate_approved: str = "Gate Approved"
    rework: str = "Rework"
    terminal: list[str] = field(default_factory=lambda: ["Done", "Closed", "Cancelled"])


@dataclass
class PromptsConfig:
    """Prompt file references.

    Attributes:
        global_prompt: Path to the global prompt .md file (optional).
        lifecycle_prompt: Path to the pre-run lifecycle template .md file (required).
            Rendered as Layer 3 of the primary work prompt (issue context, transitions).
            Defaults to "prompts/lifecycle.md".
        lifecycle_post_run_prompt: Optional path to the post-run closure template.
            When unset, defaults to ``prompts/lifecycle-post-run.md`` (see
            ``resolved_lifecycle_post_run_prompt``).
    """

    global_prompt: str | None = None
    lifecycle_prompt: str = "prompts/lifecycle.md"
    lifecycle_post_run_prompt: str | None = None

    def resolved_lifecycle_post_run_prompt(self) -> str:
        """Path to the post-run lifecycle template relative to workflow.yaml."""
        return self.lifecycle_post_run_prompt or "prompts/lifecycle-post-run.md"

    def merge_with_defaults(self, defaults: PromptsConfig) -> PromptsConfig:
        """Return new PromptsConfig with values from self overriding defaults."""
        return PromptsConfig(
            global_prompt=self.global_prompt
            if self.global_prompt is not None
            else defaults.global_prompt,
            lifecycle_prompt=self.lifecycle_prompt
            if self.lifecycle_prompt != "prompts/lifecycle.md"
            or defaults.lifecycle_prompt == "prompts/lifecycle.md"
            else defaults.lifecycle_prompt,
            lifecycle_post_run_prompt=self.lifecycle_post_run_prompt
            if self.lifecycle_post_run_prompt is not None
            else defaults.lifecycle_post_run_prompt,
        )


@dataclass
class WorkflowConfig:
    """Configuration for a single workflow.

    Attributes:
        name: The workflow identifier (e.g., "debug", "feature").
        label: The Linear label that triggers this workflow (e.g., "debug").
        default: Whether this is the default workflow for issues without matching labels.
        states: State machine definition for this workflow.
        prompts: Prompt file references for this workflow.
    """

    name: str = ""
    label: str | None = None
    default: bool = False
    states: dict[str, StateConfig] = field(default_factory=lambda: {})
    prompts: PromptsConfig = field(default_factory=PromptsConfig)


@dataclass
class StateConfig:
    """A single state in the state machine."""

    name: str = ""
    type: str = "agent"  # "agent", "agent-gate", "gate", "terminal"
    prompt: str | None = None  # path to prompt .md file
    linear_state: str = "active"  # key into LinearStatesConfig
    runner: str = "claude"
    model: str | None = None
    max_turns: int | None = None  # Merged into effective ClaudeConfig; see ClaudeConfig.max_turns.
    turn_timeout_ms: int | None = None
    stall_timeout_ms: int | None = None
    session: str = "inherit"
    permission_mode: str | None = None
    allowed_tools: list[str] | None = None
    rework_to: str | None = None  # gate only
    max_rework: int | None = None  # gate only
    default_transition: str | None = None  # agent-gate only: fallback key in transitions
    transitions: dict[str, str] = field(default_factory=lambda: {})
    hooks: HooksConfig | None = None
    # When None on type agent: treated as True. On agent-gate: must be set explicitly in YAML.
    post_run: bool | None = None


@dataclass
class WorkflowDefinition:
    config: ServiceConfig
    prompt_template: str


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
    common_prompts: PromptsConfig = field(default_factory=PromptsConfig)
    prompts: PromptsConfig = field(default_factory=PromptsConfig)
    states: dict[str, StateConfig] = field(default_factory=lambda: {})
    workflows: dict[str, WorkflowConfig] = field(default_factory=lambda: {})

    def resolved_api_key(self) -> str:
        """Resolve API key, supporting $ENV_VAR references."""
        key = self.tracker.api_key
        if not key:
            return os.environ.get("LINEAR_API_KEY", "")
        return _resolve_env(key)

    def resolved_project_slug(self) -> str:
        """Resolve project slug with env-var fallback.

        Priority: literal YAML value → $VAR reference → LINEAR_PROJECT_SLUG env var.
        """
        slug = self.tracker.project_slug
        if not slug:
            return os.environ.get("LINEAR_PROJECT_SLUG", "")
        resolved = _resolve_env(slug)
        if resolved:
            return resolved
        return os.environ.get("LINEAR_PROJECT_SLUG", "")

    def create_tracker_client(self):
        """Create and return a tracker client based on configuration.

        Uses the TrackerFactory to instantiate the appropriate client
        based on tracker.kind configuration.

        Returns:
            TrackerClient instance configured from workflow.yaml
        """
        from .tracker import TrackerFactory  # Import here to avoid circular imports

        config_dict = {
            "endpoint": self.tracker.endpoint,
            "api_key": self.resolved_api_key(),
            "project_slug": self.resolved_project_slug(),
            **self.tracker.extra,
        }
        return TrackerFactory.create_client(self.tracker.kind, config_dict)

    def agent_env(self) -> dict[str, str]:
        """Build env vars to pass to agent subprocesses.

        Includes the parent process env plus tracker config from workflow.yaml,
        so agents can connect to the tracker using the same credentials as Stokowski.
        """
        env = dict(os.environ)
        api_key = self.resolved_api_key()
        if api_key:
            env["LINEAR_API_KEY"] = api_key
        # Resolve project_slug and endpoint if they contain $VAR references
        project_slug = self.resolved_project_slug()
        if project_slug:
            env["LINEAR_PROJECT_SLUG"] = project_slug
        endpoint = _resolve_env(self.tracker.endpoint)
        if endpoint:
            env["LINEAR_ENDPOINT"] = endpoint
        # Pass tracker kind for agent awareness
        env["TRACKER_KIND"] = self.tracker.kind
        return env

    @property
    def entry_state(self) -> str | None:
        """Return the first agent or agent-gate state (first key in states dict)."""
        for name, sc in self.states.items():
            if _is_agent_like(sc):
                return name
        return None

    def active_linear_states(self) -> list[str]:
        """Return Linear state names that should be polled for candidates.

        Includes the todo state (pickup) and all agent state mappings.
        In multi-workflow mode, collects states from all workflows.
        """
        ls = self.linear_states
        seen: list[str] = []
        # Always include the todo state so new issues get picked up
        if ls.todo and ls.todo not in seen:
            seen.append(ls.todo)

        # Collect agent / agent-gate states from root config (legacy mode)
        for sc in self.states.values():
            if _is_agent_like(sc):
                linear_name = _resolve_linear_state_name(sc.linear_state, ls)
                if linear_name and linear_name not in seen:
                    seen.append(linear_name)

        # Collect agent / agent-gate states from all workflows (multi-workflow mode)
        for wf in self.workflows.values():
            for sc in wf.states.values():
                if _is_agent_like(sc):
                    linear_name = _resolve_linear_state_name(sc.linear_state, ls)
                    if linear_name and linear_name not in seen:
                        seen.append(linear_name)
        return seen

    def gate_linear_states(self) -> list[str]:
        """Return Linear state names for all gate states.

        In multi-workflow mode, collects states from all workflows.
        """
        ls = self.linear_states
        seen: list[str] = []

        # Collect gate states from root config (legacy mode)
        for sc in self.states.values():
            if sc.type == "gate":
                linear_name = _resolve_linear_state_name(sc.linear_state, ls)
                if linear_name and linear_name not in seen:
                    seen.append(linear_name)

        # Collect gate states from all workflows (multi-workflow mode)
        for wf in self.workflows.values():
            for sc in wf.states.values():
                if sc.type == "gate":
                    linear_name = _resolve_linear_state_name(sc.linear_state, ls)
                    if linear_name and linear_name not in seen:
                        seen.append(linear_name)
        return seen

    def terminal_linear_states(self) -> list[str]:
        """Return the terminal Linear state names."""
        return list(self.linear_states.terminal)

    def get_workflow_for_issue(self, issue: Any) -> WorkflowConfig:
        """Route an issue to its workflow based on labels.

        Args:
            issue: The Linear issue with labels attribute.

        Returns:
            The matching WorkflowConfig.

        Raises:
            ValueError: If no workflow matches and no default exists.
        """
        labels = getattr(issue, "labels", []) or []

        # If using multi-workflow mode (workflows: section exists)
        if self.workflows:
            # First match wins (YAML order)
            for _name, wf in self.workflows.items():
                if wf.label and wf.label in labels:
                    return wf
            # Fallback to default workflow
            for _name, wf in self.workflows.items():
                if wf.default:
                    return wf
            raise ValueError(
                f"No workflow matches issue labels {labels} and no default workflow defined"
            )

        # Legacy single-workflow mode: create implicit workflow from root config
        return WorkflowConfig(
            name="default",
            default=True,
            states=self.states,
            prompts=self.prompts,
        )

    def get_default_workflow_name(self) -> str | None:
        """Return the name of the default workflow, if any."""
        if self.workflows:
            for name, wf in self.workflows.items():
                if wf.default:
                    return name
        return None if self.workflows else "default"

    def entry_state_for_workflow(self, workflow: WorkflowConfig) -> str | None:
        """Return the first agent or agent-gate state for a workflow."""
        for name, sc in workflow.states.items():
            if _is_agent_like(sc):
                return name
        return None


def _is_agent_like(sc: StateConfig) -> bool:
    """True for states that run the agent runner (poll active Linear states)."""
    return sc.type in ("agent", "agent-gate")


def effective_post_run(state: StateConfig) -> bool:
    """Whether the orchestrator should run a post-run follow-up after the work turn.

    ``agent`` states default to True when ``post_run`` is omitted. ``agent-gate`` must
    declare ``post_run`` in YAML (enforced by ``validate_config``); if omitted, treat
    as False until validation runs.
    """
    if state.post_run is not None:
        return bool(state.post_run)
    return state.type == "agent"


def _resolve_linear_state_name(key: str, ls: LinearStatesConfig) -> str:
    """Resolve a logical state key to the actual Linear state name."""
    mapping: dict[str, str] = {
        "active": ls.active,
        "review": ls.review,
        "gate_approved": ls.gate_approved,
        "rework": ls.rework,
    }
    return mapping.get(key, key)


def _resolve_env(val: str) -> str:  # type: ignore[reportUnusedFunction]
    """Resolve environment variable references. Kept for backwards compatibility."""
    if val.startswith("$"):
        return os.environ.get(val[1:], "")
    return val


def _coerce_int(val: Any, default: int) -> int:
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _coerce_list(val: Any) -> list[str]:
    if isinstance(val, list):
        return [str(v) for v in val]  # type: ignore[misc]
    if isinstance(val, str):
        return [s.strip() for s in val.split(",") if s.strip()]
    return []


def _parse_hooks(raw: dict[str, Any] | None) -> HooksConfig | None:
    """Parse a hooks dict into HooksConfig, returning None if empty."""
    if not raw:
        return None
    return HooksConfig(
        after_create=raw.get("after_create"),
        before_run=raw.get("before_run"),
        after_run=raw.get("after_run"),
        before_remove=raw.get("before_remove"),
        on_stage_enter=raw.get("on_stage_enter"),
        timeout_ms=_coerce_int(raw.get("timeout_ms"), 60_000),
    )


def _parse_state_config(name: str, raw: dict[str, Any]) -> StateConfig:
    """Parse a single state entry from YAML into StateConfig."""
    allowed = raw.get("allowed_tools")
    hooks_raw = raw.get("hooks")

    return StateConfig(
        name=name,
        type=str(raw.get("type", "agent")),
        prompt=raw.get("prompt"),
        linear_state=str(raw.get("linear_state", "active")),
        runner=str(raw.get("runner", "claude")),
        model=raw.get("model"),
        max_turns=raw.get("max_turns"),
        turn_timeout_ms=raw.get("turn_timeout_ms"),
        stall_timeout_ms=raw.get("stall_timeout_ms"),
        session=str(raw.get("session", "inherit")),
        permission_mode=raw.get("permission_mode"),
        allowed_tools=_coerce_list(allowed) if allowed is not None else None,
        rework_to=raw.get("rework_to"),
        max_rework=raw.get("max_rework"),
        default_transition=raw.get("default_transition"),
        transitions=raw.get("transitions") or {},
        hooks=_parse_hooks(hooks_raw) if hooks_raw else None,
        post_run=(bool(raw["post_run"]) if "post_run" in raw else None),
    )


def merge_state_config(
    state: StateConfig, root_claude: ClaudeConfig, root_hooks: HooksConfig
) -> tuple[ClaudeConfig, HooksConfig]:
    """Merge state overrides with root defaults. Returns (claude_cfg, hooks_cfg)."""
    claude = ClaudeConfig(
        command=root_claude.command,
        permission_mode=state.permission_mode or root_claude.permission_mode,
        allowed_tools=state.allowed_tools
        if state.allowed_tools is not None
        else root_claude.allowed_tools,
        model=state.model or root_claude.model,
        max_turns=state.max_turns if state.max_turns is not None else root_claude.max_turns,
        turn_timeout_ms=state.turn_timeout_ms
        if state.turn_timeout_ms is not None
        else root_claude.turn_timeout_ms,
        stall_timeout_ms=state.stall_timeout_ms
        if state.stall_timeout_ms is not None
        else root_claude.stall_timeout_ms,
        append_system_prompt=root_claude.append_system_prompt,
    )
    hooks = state.hooks if state.hooks is not None else root_hooks
    return claude, hooks


def parse_workflow_file(path: str | Path) -> WorkflowDefinition:
    """Parse a workflow file (.yaml/.yml or .md with front matter) into config."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Workflow file not found: {path}")

    content = path.read_text()
    config_raw: dict[str, Any] = {}
    prompt_body = ""

    # Detect format: pure YAML or markdown with front matter
    if path.suffix in (".yaml", ".yml"):
        config_raw = yaml.safe_load(content) or {}
    elif content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            config_raw = yaml.safe_load(parts[1]) or {}
            prompt_body = parts[2]
    else:
        # Try parsing as pure YAML
        config_raw = yaml.safe_load(content) or {}

    prompt_template = prompt_body.strip()

    # Parse tracker
    t: dict[str, Any] = config_raw.get("tracker", {}) or {}  # type: ignore[assignment]
    tracker = TrackerConnectionConfig(
        kind=str(t.get("kind", "linear")),
        endpoint=str(t.get("endpoint", "https://api.linear.app/graphql")),
        api_key=str(t.get("api_key", "")),
        project_slug=str(t.get("project_slug", "")),
        extra={
            k: v for k, v in t.items() if k not in ("kind", "endpoint", "api_key", "project_slug")
        },
    )

    # Parse polling
    p: dict[str, Any] = config_raw.get("polling", {}) or {}  # type: ignore[assignment]
    polling = PollingConfig(interval_ms=_coerce_int(p.get("interval_ms"), 30_000))

    # Parse workspace
    w: dict[str, Any] = config_raw.get("workspace", {}) or {}  # type: ignore[assignment]
    workspace = WorkspaceConfig(root=str(w.get("root", "")))

    # Parse hooks
    h: dict[str, Any] = config_raw.get("hooks", {}) or {}  # type: ignore[assignment]
    hooks = HooksConfig(
        after_create=h.get("after_create"),
        before_run=h.get("before_run"),
        after_run=h.get("after_run"),
        before_remove=h.get("before_remove"),
        on_stage_enter=h.get("on_stage_enter"),
        timeout_ms=_coerce_int(h.get("timeout_ms"), 60_000),
    )

    # Parse claude
    c: dict[str, Any] = config_raw.get("claude", {}) or {}  # type: ignore[assignment]
    claude = ClaudeConfig(
        command=str(c.get("command", "claude")),
        permission_mode=str(c.get("permission_mode", "auto")),
        allowed_tools=_coerce_list(c.get("allowed_tools"))
        or ["Bash", "Read", "Edit", "Write", "Glob", "Grep"],
        model=c.get("model"),
        max_turns=_coerce_int(c.get("max_turns"), 20),
        turn_timeout_ms=_coerce_int(c.get("turn_timeout_ms"), 3_600_000),
        stall_timeout_ms=_coerce_int(c.get("stall_timeout_ms"), 300_000),
        append_system_prompt=c.get("append_system_prompt"),
    )

    # Parse agent
    a: dict[str, Any] = config_raw.get("agent", {}) or {}  # type: ignore[assignment]
    agent = AgentConfig(
        max_concurrent_agents=_coerce_int(a.get("max_concurrent_agents"), 5),
        max_retry_backoff_ms=_coerce_int(a.get("max_retry_backoff_ms"), 300_000),
        max_concurrent_agents_by_state=a.get("max_concurrent_agents_by_state") or {},
    )

    # Parse server
    s: dict[str, Any] = config_raw.get("server", {}) or {}  # type: ignore[assignment]
    server = ServerConfig(port=s.get("port"))

    # Parse linear_states
    ls_raw: dict[str, Any] = config_raw.get("linear_states", {}) or {}  # type: ignore[assignment]
    linear_states = LinearStatesConfig(
        todo=str(ls_raw.get("todo", "Todo")),
        active=str(ls_raw.get("active", "In Progress")),
        review=str(ls_raw.get("review", "Human Review")),
        gate_approved=str(ls_raw.get("gate_approved", "Gate Approved")),
        rework=str(ls_raw.get("rework", "Rework")),
        terminal=_coerce_list(ls_raw.get("terminal")) or ["Done", "Closed", "Cancelled"],
    )

    # Parse prompts
    pr_raw: dict[str, Any] = config_raw.get("prompts", {}) or {}  # type: ignore[assignment]
    lifecycle_prompt = str(pr_raw.get("lifecycle_prompt", "prompts/lifecycle.md"))
    prompts = PromptsConfig(
        global_prompt=pr_raw.get("global_prompt"),
        lifecycle_prompt=lifecycle_prompt,
        lifecycle_post_run_prompt=pr_raw.get("lifecycle_post_run_prompt"),
    )

    # Parse common_prompts (defaults for all workflows)
    cp_raw: dict[str, Any] = config_raw.get("common_prompts", {}) or {}  # type: ignore[assignment]
    common_prompts = PromptsConfig(
        global_prompt=cp_raw.get("global_prompt"),
        lifecycle_prompt=str(cp_raw.get("lifecycle_prompt", "prompts/lifecycle.md")),
        lifecycle_post_run_prompt=cp_raw.get("lifecycle_post_run_prompt"),
    )

    # Parse states
    states_raw: dict[str, Any] = config_raw.get("states", {}) or {}  # type: ignore[assignment]
    states: dict[str, StateConfig] = {}
    for state_name, state_data in states_raw.items():
        sd: dict[str, Any] = state_data or {}  # type: ignore[assignment]
        states[state_name] = _parse_state_config(state_name, sd)

    # Parse workflows section (multi-workflow mode)
    workflows_raw: dict[str, Any] | None = config_raw.get("workflows")  # type: ignore[assignment]
    workflows: dict[str, WorkflowConfig] = {}
    if workflows_raw:
        for wf_name, wf_data in workflows_raw.items():
            wf_states: dict[str, StateConfig] = {}
            wf_states_raw: dict[str, Any] = wf_data.get("states", {})  # type: ignore[assignment]
            for state_name, state_data in wf_states_raw.items():
                sd: dict[str, Any] = state_data or {}  # type: ignore[assignment]
                wf_states[state_name] = _parse_state_config(state_name, sd)

            wf_prompts_raw: dict[str, Any] = wf_data.get("prompts", {}) or {}  # type: ignore[assignment]
            wf_prompts_explicit = PromptsConfig(
                global_prompt=wf_prompts_raw.get("global_prompt"),
                lifecycle_prompt=str(
                    wf_prompts_raw.get("lifecycle_prompt", "prompts/lifecycle.md")
                ),
                lifecycle_post_run_prompt=wf_prompts_raw.get("lifecycle_post_run_prompt"),
            )
            # Merge with common_prompts - workflow takes precedence
            wf_prompts = wf_prompts_explicit.merge_with_defaults(common_prompts)

            workflows[wf_name] = WorkflowConfig(
                name=wf_name,
                label=wf_data.get("label"),
                default=wf_data.get("default", False),
                states=wf_states,
                prompts=wf_prompts,
            )

    cfg = ServiceConfig(
        tracker=tracker,
        polling=polling,
        workspace=workspace,
        hooks=hooks,
        claude=claude,
        agent=agent,
        server=server,
        linear_states=linear_states,
        common_prompts=common_prompts,
        prompts=prompts,
        states=states,
        workflows=workflows,
    )

    return WorkflowDefinition(config=cfg, prompt_template=prompt_template)


def _validate_agent_gate_rules(
    msg_prefix: str,
    sc: StateConfig,
    states_by_name: dict[str, StateConfig],
    errors: list[str],
) -> None:
    """Validate agent-gate-specific constraints (shared by legacy and multi-workflow)."""
    if not sc.prompt:
        errors.append(f"{msg_prefix} (agent-gate) is missing 'prompt' field")
    if sc.rework_to:
        errors.append(
            f"{msg_prefix} (agent-gate) must not set 'rework_to' (reserved for gate states)"
        )
    if sc.max_rework is not None:
        errors.append(
            f"{msg_prefix} (agent-gate) must not set 'max_rework' (reserved for gate states)"
        )
    if not sc.transitions:
        errors.append(f"{msg_prefix} (agent-gate) must declare at least one transition")
    if not sc.default_transition:
        errors.append(f"{msg_prefix} (agent-gate) is missing 'default_transition'")
    elif sc.default_transition not in sc.transitions:
        errors.append(
            f"{msg_prefix} (agent-gate) default_transition '{sc.default_transition}' "
            f"must be a key in transitions"
        )
    else:
        target_name = sc.transitions[sc.default_transition]
        target_cfg = states_by_name.get(target_name)
        if target_cfg is not None and target_cfg.type != "gate":
            errors.append(
                f"{msg_prefix} (agent-gate) default_transition must target a state with "
                f"type 'gate', not '{target_cfg.type}' (target '{target_name}')"
            )
    if sc.post_run is None:
        errors.append(
            f"{msg_prefix} (agent-gate) must declare 'post_run' (true or false); "
            "typical routing gates use post_run: false"
        )


def validate_config(cfg: ServiceConfig, skip_secrets_check: bool = False) -> list[str]:
    """Validate state machine config for dispatch readiness. Returns list of errors.

    Args:
        cfg: The service configuration to validate.
        skip_secrets_check: If True, skip validation of API keys and secrets.
            Useful for CI/testing where secrets are not available.
    """
    errors: list[str] = []

    # Basic tracker checks
    if cfg.tracker.kind != "linear":
        errors.append(f"Unsupported tracker kind: {cfg.tracker.kind}")
    if not skip_secrets_check and not cfg.resolved_api_key():
        errors.append("Missing tracker API key (set LINEAR_API_KEY or tracker.api_key)")
    if not cfg.resolved_project_slug():
        errors.append(
            "Missing tracker.project_slug (set LINEAR_PROJECT_SLUG or tracker.project_slug)"
        )

    # In legacy mode, root states must be defined
    # In multi-workflow mode, workflows must have states (validated per workflow below)
    if not cfg.states and not cfg.workflows:
        errors.append("No states or workflows defined")
        return errors

    # Valid linear_state keys
    valid_linear_keys = {"active", "review", "gate_approved", "rework", "terminal"}

    # Validate root states (legacy mode) - only if workflows not defined
    has_agent = False
    has_terminal = False
    all_state_names = set(cfg.states.keys())

    for name, sc in cfg.states.items():
        # Check type
        if sc.type not in ("agent", "agent-gate", "gate", "terminal"):
            errors.append(f"State '{name}' has invalid type: {sc.type}")
            continue

        if sc.type == "agent":
            has_agent = True
            # Agent states should have a prompt
            if not sc.prompt:
                errors.append(f"Agent state '{name}' is missing 'prompt' field")

        elif sc.type == "agent-gate":
            has_agent = True
            _validate_agent_gate_rules(f"State '{name}'", sc, cfg.states, errors)

        elif sc.type == "gate":
            # Gates must have rework_to
            if not sc.rework_to:
                errors.append(f"Gate state '{name}' is missing 'rework_to' field")
            elif sc.rework_to not in all_state_names:
                errors.append(
                    f"Gate state '{name}' rework_to target '{sc.rework_to}' is not a defined state"
                )
            # Gates must have approve transition
            if "approve" not in sc.transitions:
                errors.append(f"Gate state '{name}' is missing 'approve' transition")

        elif sc.type == "terminal":
            has_terminal = True

        # Validate linear_state key
        if sc.linear_state not in valid_linear_keys:
            errors.append(
                f"State '{name}' has invalid linear_state: '{sc.linear_state}' "
                f"(valid: {', '.join(sorted(valid_linear_keys))})"
            )

        # Validate all transitions point to existing states
        for trigger, target in sc.transitions.items():
            if target not in all_state_names:
                errors.append(
                    f"State '{name}' transition '{trigger}' points to unknown state '{target}'"
                )

    # Only require root agent/terminal states in legacy mode
    if not cfg.workflows:
        if not has_agent:
            errors.append(
                "No agent states defined (need at least one state with type 'agent' or 'agent-gate')"
            )
        if not has_terminal:
            errors.append(
                "No terminal states defined (need at least one state with type 'terminal')"
            )

    # Warn about unreachable states (non-entry states that no transition points to)
    entry = cfg.entry_state
    reachable: set[str] = set()
    if entry:
        reachable.add(entry)
    for sc in cfg.states.values():
        for target in sc.transitions.values():
            reachable.add(target)
        if sc.rework_to:
            reachable.add(sc.rework_to)

    unreachable = all_state_names - reachable
    for name in unreachable:
        log.warning("State '%s' is unreachable (no transitions lead to it)", name)

    # Validate multi-workflow configuration
    if cfg.workflows:
        # Check for multiple default workflows
        default_workflows = [name for name, wf in cfg.workflows.items() if wf.default]
        if len(default_workflows) > 1:
            errors.append(f"Multiple workflows marked as default: {', '.join(default_workflows)}")

        # Check for duplicate labels across workflows
        label_to_workflows: dict[str, list[str]] = {}
        for wf_name, wf in cfg.workflows.items():
            if wf.label:
                label_to_workflows.setdefault(wf.label, []).append(wf_name)
        for label, wf_names in label_to_workflows.items():
            if len(wf_names) > 1:
                errors.append(
                    f"Multiple workflows have the same label '{label}': {', '.join(wf_names)}"
                )

        # Validate each workflow's state machine
        for wf_name, wf in cfg.workflows.items():
            if not wf.states:
                errors.append(f"Workflow '{wf_name}' has no states defined")
                continue

            wf_has_agent = False
            wf_has_terminal = False
            wf_state_names = set(wf.states.keys())

            for state_name, sc in wf.states.items():
                # Check type
                if sc.type not in ("agent", "agent-gate", "gate", "terminal"):
                    errors.append(
                        f"Workflow '{wf_name}' state '{state_name}' has invalid type: {sc.type}"
                    )
                    continue

                if sc.type == "agent":
                    wf_has_agent = True
                    if not sc.prompt:
                        errors.append(
                            f"Workflow '{wf_name}' agent state '{state_name}' is missing 'prompt' field"
                        )

                elif sc.type == "agent-gate":
                    wf_has_agent = True
                    _validate_agent_gate_rules(
                        f"Workflow '{wf_name}' state '{state_name}'",
                        sc,
                        wf.states,
                        errors,
                    )

                elif sc.type == "gate":
                    if not sc.rework_to:
                        errors.append(
                            f"Workflow '{wf_name}' gate state '{state_name}' is missing 'rework_to' field"
                        )
                    elif sc.rework_to not in wf_state_names:
                        errors.append(
                            f"Workflow '{wf_name}' gate state '{state_name}' rework_to target '{sc.rework_to}' "
                            f"is not a defined state"
                        )
                    if "approve" not in sc.transitions:
                        errors.append(
                            f"Workflow '{wf_name}' gate state '{state_name}' is missing 'approve' transition"
                        )

                elif sc.type == "terminal":
                    wf_has_terminal = True

                # Validate linear_state key
                if sc.linear_state not in valid_linear_keys:
                    errors.append(
                        f"Workflow '{wf_name}' state '{state_name}' has invalid linear_state: '{sc.linear_state}' "
                        f"(valid: {', '.join(sorted(valid_linear_keys))})"
                    )

                # Validate transitions
                for trigger, target in sc.transitions.items():
                    if target not in wf_state_names:
                        errors.append(
                            f"Workflow '{wf_name}' state '{state_name}' transition '{trigger}' points to "
                            f"unknown state '{target}'"
                        )

            if not wf_has_agent:
                errors.append(f"Workflow '{wf_name}' has no agent states defined")
            if not wf_has_terminal:
                errors.append(f"Workflow '{wf_name}' has no terminal states defined")

    return errors
