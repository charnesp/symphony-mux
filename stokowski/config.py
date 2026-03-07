"""Workflow loader and typed configuration."""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class TrackerConfig:
    kind: str = "linear"
    endpoint: str = "https://api.linear.app/graphql"
    api_key: str = ""
    project_slug: str = ""
    active_states: list[str] = field(default_factory=lambda: ["Todo", "In Progress"])
    terminal_states: list[str] = field(
        default_factory=lambda: ["Closed", "Cancelled", "Canceled", "Duplicate", "Done"]
    )


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
    timeout_ms: int = 60_000


@dataclass
class ClaudeConfig:
    command: str = "claude"
    permission_mode: str = "auto"  # "auto" or "allowedTools"
    allowed_tools: list[str] = field(
        default_factory=lambda: ["Bash", "Read", "Edit", "Write", "Glob", "Grep"]
    )
    model: str | None = None
    max_turns: int = 20
    turn_timeout_ms: int = 3_600_000
    stall_timeout_ms: int = 300_000
    append_system_prompt: str | None = None


@dataclass
class AgentConfig:
    max_concurrent_agents: int = 5
    max_retry_backoff_ms: int = 300_000
    max_concurrent_agents_by_state: dict[str, int] = field(default_factory=dict)


@dataclass
class ServerConfig:
    port: int | None = None


@dataclass
class WorkflowDefinition:
    config: ServiceConfig
    prompt_template: str


@dataclass
class ServiceConfig:
    tracker: TrackerConfig = field(default_factory=TrackerConfig)
    polling: PollingConfig = field(default_factory=PollingConfig)
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    hooks: HooksConfig = field(default_factory=HooksConfig)
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    server: ServerConfig = field(default_factory=ServerConfig)

    def resolved_api_key(self) -> str:
        key = self.tracker.api_key
        if not key:
            return os.environ.get("LINEAR_API_KEY", "")
        if key.startswith("$"):
            return os.environ.get(key[1:], "")
        return key


def _resolve_env(val: str) -> str:
    if isinstance(val, str) and val.startswith("$"):
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
        return [str(v) for v in val]
    if isinstance(val, str):
        return [s.strip() for s in val.split(",") if s.strip()]
    return []


def parse_workflow_file(path: str | Path) -> WorkflowDefinition:
    """Parse a WORKFLOW.md file into config + prompt template."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Workflow file not found: {path}")

    content = path.read_text()
    config_raw: dict[str, Any] = {}
    prompt_body = content

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            config_raw = yaml.safe_load(parts[1]) or {}
            prompt_body = parts[2]

    if not isinstance(config_raw, dict):
        raise ValueError("WORKFLOW.md front matter must be a YAML mapping")

    prompt_template = prompt_body.strip()

    # Parse tracker
    t = config_raw.get("tracker", {}) or {}
    tracker = TrackerConfig(
        kind=str(t.get("kind", "linear")),
        endpoint=str(t.get("endpoint", "https://api.linear.app/graphql")),
        api_key=str(t.get("api_key", "")),
        project_slug=str(t.get("project_slug", "")),
        active_states=_coerce_list(t.get("active_states")) or ["Todo", "In Progress"],
        terminal_states=_coerce_list(t.get("terminal_states"))
        or ["Closed", "Cancelled", "Canceled", "Duplicate", "Done"],
    )

    # Parse polling
    p = config_raw.get("polling", {}) or {}
    polling = PollingConfig(interval_ms=_coerce_int(p.get("interval_ms"), 30_000))

    # Parse workspace
    w = config_raw.get("workspace", {}) or {}
    workspace = WorkspaceConfig(root=str(w.get("root", "")))

    # Parse hooks
    h = config_raw.get("hooks", {}) or {}
    hooks = HooksConfig(
        after_create=h.get("after_create"),
        before_run=h.get("before_run"),
        after_run=h.get("after_run"),
        before_remove=h.get("before_remove"),
        timeout_ms=_coerce_int(h.get("timeout_ms"), 60_000),
    )

    # Parse claude (replaces codex)
    c = config_raw.get("claude", {}) or {}
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
    a = config_raw.get("agent", {}) or {}
    agent = AgentConfig(
        max_concurrent_agents=_coerce_int(a.get("max_concurrent_agents"), 5),
        max_retry_backoff_ms=_coerce_int(a.get("max_retry_backoff_ms"), 300_000),
        max_concurrent_agents_by_state=a.get("max_concurrent_agents_by_state") or {},
    )

    # Parse server
    s = config_raw.get("server", {}) or {}
    server = ServerConfig(port=s.get("port"))

    cfg = ServiceConfig(
        tracker=tracker,
        polling=polling,
        workspace=workspace,
        hooks=hooks,
        claude=claude,
        agent=agent,
        server=server,
    )

    return WorkflowDefinition(config=cfg, prompt_template=prompt_template)


def validate_config(cfg: ServiceConfig) -> list[str]:
    """Validate config for dispatch readiness. Returns list of errors."""
    errors = []
    if cfg.tracker.kind != "linear":
        errors.append(f"Unsupported tracker kind: {cfg.tracker.kind}")
    if not cfg.resolved_api_key():
        errors.append("Missing tracker API key (set LINEAR_API_KEY or tracker.api_key)")
    if not cfg.tracker.project_slug:
        errors.append("Missing tracker.project_slug")
    return errors
