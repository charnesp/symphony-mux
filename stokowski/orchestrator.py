"""Main orchestration loop - polls Linear, dispatches agents, manages state."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jinja2 import Environment, StrictUndefined, TemplateSyntaxError, select_autoescape

from .agent_gate_route import decide_agent_gate_transition, format_route_error_comment
from .config import (
    ServiceConfig,
    WorkflowConfig,
    WorkflowDefinition,
    merge_state_config,
    parse_workflow_file,
    validate_config,
)
from .linear import LinearClient  # noqa: F401 - triggers registration
from .models import Issue, RetryEntry, RunAttempt
from .prompt import assemble_prompt
from .reporting import extract_report, format_no_report_comment, format_report_comment
from .runner import run_turn
from .tracker import CommentsFetchError, TrackerClient
from .tracking import (
    make_gate_comment,
    make_state_comment,
    parse_latest_gate_waiting,
    parse_latest_tracking,
)
from .workspace import ensure_workspace, remove_workspace

logger = logging.getLogger("stokowski")


class Orchestrator:
    def __init__(
        self,
        workflow_path: str | Path,
        log_agent_output_dir: Path | None = None,
    ):
        self.workflow_path = Path(workflow_path)
        self.workflow: WorkflowDefinition | None = None
        self._log_agent_output_dir = log_agent_output_dir

        # Runtime state
        self.running: dict[str, RunAttempt] = {}  # issue_id -> RunAttempt
        self.claimed: set[str] = set()
        self.retry_attempts: dict[str, RetryEntry] = {}
        self.completed: set[str] = set()

        # Aggregate metrics
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_tokens: int = 0
        self.total_seconds_running: float = 0
        self._issue_input_tokens: dict[str, int] = {}
        self._issue_output_tokens: dict[str, int] = {}
        self._issue_total_tokens: dict[str, int] = {}

        # Internal
        self._tracker: TrackerClient | None = None
        self._tasks: dict[str, asyncio.Task] = {}
        self._retry_timers: dict[str, asyncio.TimerHandle] = {}
        self._child_pids: set[int] = set()  # Track claude subprocess PIDs
        self._last_session_ids: dict[str, str] = {}  # issue_id -> last known session_id
        self._last_prompt_stage_by_issue: dict[str, tuple[str, str]] = {}
        self._jinja = Environment(undefined=StrictUndefined, autoescape=select_autoescape())
        self._running = False
        self._last_issues: dict[str, Issue] = {}
        self._last_completed_at: dict[str, datetime] = {}  # issue_id -> last worker completion time

        # State machine tracking
        self._issue_current_state: dict[str, str] = {}  # issue_id -> internal state name
        self._issue_state_runs: dict[str, int] = {}  # issue_id -> run number for current state
        self._pending_gates: dict[str, str] = {}  # issue_id -> gate state name

        # Workflow cache (issue_id -> WorkflowConfig)
        self._issue_workflow_cache: dict[str, WorkflowConfig] = {}

    @property
    def cfg(self) -> ServiceConfig:
        assert self.workflow is not None
        return self.workflow.config

    def _load_workflow(self) -> list[str]:
        """Load/reload workflow file. Returns validation errors."""
        # Check if workflow config has changed
        old_workflows = set()
        if self.workflow and self.workflow.config.workflows:
            old_workflows = set(self.workflow.config.workflows.keys())

        try:
            self.workflow = parse_workflow_file(self.workflow_path)
        except Exception as e:
            return [f"Workflow load error: {e}"]

        # Clear workflow cache if workflows were renamed or removed
        # This prevents stale references after config reload
        if old_workflows:
            new_workflows = set(self.cfg.workflows.keys())
            removed_workflows = old_workflows - new_workflows
            if removed_workflows:
                logger.info(f"Workflows removed after reload: {removed_workflows}")
                # Clear cache entries referencing removed workflows
                stale_issue_ids = [
                    issue_id
                    for issue_id, wf in self._issue_workflow_cache.items()
                    if wf.name in removed_workflows
                ]
                for issue_id in stale_issue_ids:
                    del self._issue_workflow_cache[issue_id]
                    logger.debug(f"Cleared workflow cache for {issue_id}")

        return validate_config(self.cfg)

    def _ensure_tracker_client(self) -> TrackerClient:
        if self._tracker is None:
            self._tracker = self.cfg.create_tracker_client()
        return self._tracker

    async def _load_issue_comments(
        self, client: TrackerClient, issue: Issue, workspace_path: Path | None = None
    ) -> list[dict]:
        """Fetch issue comments; warn when history may be truncated.

        For LinearClient, also downloads image attachments to the workspace.

        Args:
            client: The tracker client to fetch comments from
            issue: The issue being processed
            workspace_path: The workspace path for downloading images (optional)

        Raises:
            CommentsFetchError: The first page of comments could not be loaded.
        """
        result = await client.fetch_comments(issue.id)
        if not result.complete:
            logger.warning(
                "Partial comment history for %s; tracking and workflow resolution may be stale",
                issue.identifier,
            )
        comments = result.nodes

        # Download images from attachments for LinearClient
        if workspace_path and isinstance(client, LinearClient):
            comments = await client.download_comment_images(comments, issue, workspace_path)

        return comments

    async def start(self):
        """Start the orchestration loop."""
        errors = self._load_workflow()
        if errors:
            for e in errors:
                logger.error(f"Config error: {e}")
            raise RuntimeError(f"Startup validation failed: {errors}")

        logger.info(
            f"Starting Stokowski "
            f"project={self.cfg.resolved_project_slug()} "
            f"max_agents={self.cfg.agent.max_concurrent_agents} "
            f"poll_ms={self.cfg.polling.interval_ms}"
        )

        self._running = True
        self._stop_event = asyncio.Event()

        # Startup terminal cleanup
        await self._startup_cleanup()

        # Main poll loop
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.error(f"Tick error: {e}")

            # Interruptible sleep
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.cfg.polling.interval_ms / 1000,
                )
                break  # stop_event was set
            except TimeoutError:
                pass  # Normal poll interval elapsed

    async def stop(self):
        """Stop the orchestration loop and kill all running agents."""
        self._running = False
        if hasattr(self, "_stop_event"):
            self._stop_event.set()

        # Kill all child claude processes first
        for pid in list(self._child_pids):
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                    os.kill(pid, signal.SIGKILL)
        self._child_pids.clear()

        # Cancel async tasks
        for _issue_id, task in list(self._tasks.items()):
            task.cancel()
        # Give them a moment to finish
        if self._tasks:
            await asyncio.sleep(0.5)
        self._tasks.clear()

        if self._tracker:
            await self._tracker.close()

    async def _startup_cleanup(self):
        """Remove workspaces for issues already in terminal states."""
        try:
            client = self._ensure_tracker_client()
            terminal = await client.fetch_issues_by_states(
                self.cfg.resolved_project_slug(),
                self.cfg.terminal_linear_states(),
            )
            ws_root = self.cfg.workspace.resolved_root()
            for issue in terminal:
                await remove_workspace(ws_root, issue.identifier, self.cfg.hooks)
            if terminal:
                logger.info(f"Cleaned {len(terminal)} terminal workspaces")
        except Exception as e:
            logger.warning(f"Startup cleanup failed (continuing): {e}")

    async def _resolve_workflow_for_issue(
        self, issue: Issue, tracking: dict[str, Any] | None = None
    ) -> WorkflowConfig | None:
        """Resolve workflow for an issue with caching and tracking support.

        Priority:
        1. Cache (if already resolved this session)
        2. Tracking comment (for crash recovery consistency)
        3. Fresh resolution from labels
        """
        # 1. Check memory cache
        if issue.id in self._issue_workflow_cache:
            return self._issue_workflow_cache[issue.id]

        # 2. Try to read from tracking comment (crash recovery)
        # Verify that tracked workflow still matches current labels to handle
        # cases where issue labels were changed after initial dispatch
        if tracking and "workflow" in tracking:
            workflow_name = tracking["workflow"]
            labels = getattr(issue, "labels", []) or []

            # Check if tracked workflow still matches current labels
            tracked_wf_still_valid = False
            if self.cfg.workflows and workflow_name in self.cfg.workflows:
                tracked_wf = self.cfg.workflows[workflow_name]
                # Check if labels still match this workflow
                if tracked_wf.label and tracked_wf.label in labels:
                    tracked_wf_still_valid = True
                elif tracked_wf.default and not any(
                    wf.label and wf.label in labels
                    for wf in self.cfg.workflows.values()
                    if wf.label
                ):
                    # Tracked workflow is default and no other workflow matches
                    tracked_wf_still_valid = True

                if tracked_wf_still_valid:
                    self._issue_workflow_cache[issue.id] = tracked_wf
                    return tracked_wf
                else:
                    logger.warning(
                        f"Tracked workflow '{workflow_name}' for {issue.identifier} "
                        f"no longer matches labels {labels}, will re-resolve"
                    )

            elif workflow_name == "default":
                # Legacy mode or explicit default workflow
                if self.cfg.workflows:
                    # Multi-workflow mode: find the default workflow
                    for wf in self.cfg.workflows.values():
                        if wf.default:
                            self._issue_workflow_cache[issue.id] = wf
                            return wf
                    # No default workflow found, fall through to fresh resolution
                else:
                    # Legacy mode - use implicit default workflow
                    workflow = WorkflowConfig(
                        name="default",
                        default=True,
                        states=self.cfg.states,
                        prompts=self.cfg.prompts,
                    )
                    self._issue_workflow_cache[issue.id] = workflow
                    return workflow

        # 3. Fresh resolution from labels
        try:
            workflow = self.cfg.get_workflow_for_issue(issue)
            self._issue_workflow_cache[issue.id] = workflow
            return workflow
        except ValueError as e:
            logger.error(f"Failed to resolve workflow for {issue.identifier}: {e}")
            return None

    def _workflow_for_run_attempt(self, issue: Issue, attempt: RunAttempt) -> WorkflowConfig | None:
        """Resolve workflow for a run: issue labels first, then frozen attempt name, then cache."""
        if not self.cfg.workflows:
            return WorkflowConfig(
                name="default",
                default=True,
                states=self.cfg.states,
                prompts=self.cfg.prompts,
            )
        try:
            wf = self.cfg.get_workflow_for_issue(issue)
            self._issue_workflow_cache[issue.id] = wf
            return wf
        except ValueError:
            pass
        name = attempt.workflow_name
        if name and name in self.cfg.workflows:
            wf = self.cfg.workflows[name]
            self._issue_workflow_cache[issue.id] = wf
            return wf
        cached = self._issue_workflow_cache.get(issue.id)
        if cached is not None:
            return cached
        logger.error(
            f"Cannot resolve workflow for {issue.identifier} "
            f"(workflow_name={attempt.workflow_name!r}, labels={getattr(issue, 'labels', [])})"
        )
        return None

    def _workflow_name_undefined_in_config(
        self, issue: Issue, attempt: RunAttempt
    ) -> tuple[bool, str | None]:
        """True when the run records a workflow key missing from the current config (config error)."""
        if not self.cfg.workflows or not attempt.workflow_name:
            return False, None
        if attempt.workflow_name in self.cfg.workflows:
            return False, None
        ctx = (
            f"worker exit (config error: workflow_name '{attempt.workflow_name}' is not defined "
            f"in the current workflow configuration; issue={issue.identifier})"
        )
        return True, ctx

    def _workflow_label_mismatch_after_run(
        self, issue: Issue, attempt: RunAttempt
    ) -> tuple[bool, str | None]:
        """True when labels map to a different workflow key than the dispatched run (config error)."""
        if not self.cfg.workflows or not attempt.workflow_name:
            return False, None
        if attempt.workflow_name not in self.cfg.workflows:
            return False, None
        try:
            wf_labels = self.cfg.get_workflow_for_issue(issue)
        except ValueError:
            return False, None
        if wf_labels.name == attempt.workflow_name:
            return False, None
        ctx = (
            f"worker exit (config error: label/workflow mismatch: run was dispatched as "
            f"'{attempt.workflow_name}', issue labels now resolve to '{wf_labels.name}')"
        )
        return True, ctx

    async def _resolve_current_state(self, issue: Issue) -> tuple[str, int]:
        """Resolve current state machine state for an issue.
        Returns (state_name, run).
        """
        # Check cache first
        if issue.id in self._issue_current_state:
            state_name = self._issue_current_state[issue.id]
            run = self._issue_state_runs.get(issue.id, 1)
            return state_name, run

        # Fetch comments from Linear and parse latest tracking
        client = self._ensure_tracker_client()
        comments = await self._load_issue_comments(client, issue)
        tracking = parse_latest_tracking(comments)

        # Resolve workflow first (for workflow-scoped state lookup)
        workflow = await self._resolve_workflow_for_issue(issue, tracking)
        if workflow is None:
            raise RuntimeError(f"No workflow found for issue {issue.identifier}")

        # Get entry state from the specific workflow
        entry = self.cfg.entry_state_for_workflow(workflow)
        if entry is None:
            raise RuntimeError("No entry state defined in config")

        # Use workflow-scoped states for lookup
        workflow_states = workflow.states

        # No tracking → entry state, run 1
        if tracking is None:
            self._issue_current_state[issue.id] = entry
            self._issue_state_runs[issue.id] = 1
            return entry, 1

        if tracking["type"] == "state":
            state_name = tracking.get("state", entry)
            run = tracking.get("run", 1)
            if state_name in workflow_states:
                self._issue_current_state[issue.id] = state_name
                self._issue_state_runs[issue.id] = run
                return state_name, run
            # Unknown state → fallback to entry
            self._issue_current_state[issue.id] = entry
            self._issue_state_runs[issue.id] = 1
            return entry, 1

        if tracking["type"] == "gate":
            gate_state = tracking.get("state", "")
            status = tracking.get("status", "")
            run = tracking.get("run", 1)

            if status == "waiting":
                if gate_state in workflow_states:
                    self._issue_current_state[issue.id] = gate_state
                    self._issue_state_runs[issue.id] = run
                    self._pending_gates[issue.id] = gate_state
                    return gate_state, run

            elif status == "approved":
                gate_cfg = workflow_states.get(gate_state)
                if gate_cfg and "approve" in gate_cfg.transitions:
                    target = gate_cfg.transitions["approve"]
                    self._issue_current_state[issue.id] = target
                    self._issue_state_runs[issue.id] = run
                    return target, run

            elif status == "rework":
                gate_cfg = workflow_states.get(gate_state)
                rework_to = tracking.get("rework_to", "")
                if not rework_to and gate_cfg:
                    rework_to = gate_cfg.rework_to or ""
                if rework_to and rework_to in workflow_states:
                    self._issue_current_state[issue.id] = rework_to
                    self._issue_state_runs[issue.id] = run
                    return rework_to, run

        # Fallback to entry state
        self._issue_current_state[issue.id] = entry
        self._issue_state_runs[issue.id] = 1
        return entry, 1

    async def _handle_orphaned_issue(
        self,
        issue: Issue,
        context: str,
        *,
        release_agent_resources: bool = False,
    ):
        """Handle an issue whose workflow is no longer available.

        Moves the issue to a terminal state and posts a comment explaining
        the situation. Prevents issues from getting stuck in limbo.
        """
        logger.warning(f"Handling orphaned issue={issue.identifier} context={context}")
        client = self._ensure_tracker_client()

        # Move to terminal state
        terminal_state = (
            self.cfg.terminal_linear_states()[0] if self.cfg.terminal_linear_states() else "Done"
        )
        try:
            moved = await client.update_issue_state(issue.id, terminal_state)
            if moved:
                logger.info(f"Moved orphaned {issue.identifier} to {terminal_state}")
            else:
                logger.warning(f"Failed to move orphaned {issue.identifier} to terminal")
        except Exception as e:
            logger.error(f"Failed to handle orphaned issue {issue.identifier}: {e}")

        # Post explanatory comment
        try:
            extra = ""
            ctx_l = context.lower()
            if "after agent failure" in ctx_l:
                extra = (
                    "The agent run ended with failed, timed out, or stalled status, and Stokowski "
                    "could not resolve which workflow applies "
                    "(e.g. labels changed, missing `workflow_name` on the run, or config mismatch). "
                )
            elif "label/workflow mismatch" in ctx_l:
                extra = (
                    "The Linear labels on this issue now map to a different workflow than the one "
                    "used when the agent run was started. Stokowski cannot safely apply transitions "
                    "or parse agent-gate output against the wrong machine. "
                )
            elif "not defined" in ctx_l and "workflow_name" in ctx_l:
                extra = (
                    "This run was recorded against a workflow key that is not defined in the "
                    "current workflow.yaml (rename, removal, or typo). "
                )
            elif "gate state could not be recovered" in ctx_l:
                extra = (
                    "Stokowski could not determine which gate state applied "
                    "(no in-memory pending gate and no waiting gate tracking on the issue). "
                )
            elif "worker exit" in ctx_l:
                extra = (
                    "Stokowski could not resolve which workflow applies after the agent run "
                    "(e.g. labels changed, missing `workflow_name` on the run, or config mismatch). "
                )
            comment = (
                f"**[Stokowski]** ⚠️ Configuration Error\n\n"
                f"{extra}"
                f"This issue's workflow is no longer available (detected during {context}). "
                f"The issue has been moved to '{terminal_state}'. "
                f"Please check the workflow configuration."
            )
            await client.post_comment(issue.id, comment)
        except Exception as e:
            logger.warning(f"Failed to post orphan comment for {issue.identifier}: {e}")

        # Clean up tracking state
        self._issue_current_state.pop(issue.id, None)
        self._issue_state_runs.pop(issue.id, None)
        self._pending_gates.pop(issue.id, None)
        self._issue_workflow_cache.pop(issue.id, None)
        self._issue_input_tokens.pop(issue.id, None)
        self._issue_output_tokens.pop(issue.id, None)
        self._issue_total_tokens.pop(issue.id, None)

        if release_agent_resources:
            self._last_session_ids.pop(issue.id, None)
            self._last_prompt_stage_by_issue.pop(issue.id, None)
            self.claimed.discard(issue.id)
            self.completed.add(issue.id)
            try:
                ws_root = self.cfg.workspace.resolved_root()
                await remove_workspace(ws_root, issue.identifier, self.cfg.hooks)
            except Exception as e:
                logger.warning(f"Failed to remove workspace for orphaned {issue.identifier}: {e}")

    async def _safe_orphan_from_worker_exit(self, issue: Issue, context: str) -> None:
        """Orphan handler for post-worker exit; releases claim and workspace like terminal."""
        try:
            await self._handle_orphaned_issue(
                issue,
                context,
                release_agent_resources=True,
            )
        except Exception as e:
            logger.error(
                f"Orphan handling failed issue={issue.identifier} context={context}: {e}",
                exc_info=True,
            )
            self.claimed.discard(issue.id)

    async def _safe_enter_gate(
        self, issue: Issue, state_name: str, workflow_name: str | None = None
    ):
        """Wrapper around _enter_gate that logs errors."""
        try:
            await self._enter_gate(issue, state_name, workflow_name)
        except Exception as e:
            logger.error(
                f"Enter gate failed issue={issue.identifier} gate={state_name}: {e}",
                exc_info=True,
            )

    async def _enter_gate(self, issue: Issue, state_name: str, workflow_name: str | None = None):
        """Move issue to gate state and post tracking comment."""
        # Get workflow config to access workflow-scoped states
        try:
            workflow = self.cfg.get_workflow_for_issue(issue)
        except ValueError as e:
            logger.error(f"Cannot enter gate for {issue.identifier}: {e}")
            self.claimed.discard(issue.id)
            self._issue_workflow_cache.pop(issue.id, None)
            return

        # Cache the workflow for this issue
        self._issue_workflow_cache[issue.id] = workflow

        state_cfg = workflow.states.get(state_name)
        prompt = state_cfg.prompt if state_cfg else ""
        run = self._issue_state_runs.get(issue.id, 1)

        client = self._ensure_tracker_client()

        comment = make_gate_comment(
            state=state_name,
            status="waiting",
            prompt=prompt or "",
            run=run,
            workflow=workflow_name or workflow.name if workflow else None,
        )
        await client.post_comment(issue.id, comment)

        review_state = self.cfg.linear_states.review
        moved = await client.update_issue_state(issue.id, review_state)
        if not moved:
            logger.error(
                f"Failed to move {issue.identifier} to review state '{review_state}' "
                f"— issue will remain claimed to prevent re-dispatch loop"
            )
            # Keep claimed so the issue doesn't get re-dispatched while
            # still in the active Linear state. Track the gate so
            # _handle_gate_responses can pick it up if the state is
            # changed manually.
            self._pending_gates[issue.id] = state_name
            self._issue_current_state[issue.id] = state_name
            self.running.pop(issue.id, None)
            self._tasks.pop(issue.id, None)
            # Schedule a retry to attempt the state move again
            self._schedule_retry(issue, attempt_num=0, delay_ms=10_000)
            return

        self._pending_gates[issue.id] = state_name
        self._issue_current_state[issue.id] = state_name
        # Release from running/claimed so it doesn't block slots
        self.running.pop(issue.id, None)
        self._tasks.pop(issue.id, None)
        self.claimed.discard(issue.id)

        logger.info(f"Gate entered issue={issue.identifier} gate={state_name} run={run}")

    async def _safe_transition(self, issue: Issue, transition_name: str):
        """Wrapper around _transition that logs errors instead of silently swallowing them."""
        try:
            await self._transition(issue, transition_name)
        except Exception as e:
            logger.error(
                f"Transition failed issue={issue.identifier} transition={transition_name}: {e}",
                exc_info=True,
            )
            # Release claimed so the issue can be retried on next tick
            self.claimed.discard(issue.id)

    async def _transition(self, issue: Issue, transition_name: str):
        """Follow a transition from the current state.

        Handles target types:
        - terminal → move to Done, clean workspace, release tracking
        - gate → enter gate
        - agent / agent-gate → post state comment, ensure active Linear state, schedule retry
        """
        current_state_name = self._issue_current_state.get(issue.id)
        if not current_state_name:
            logger.warning(f"No current state for {issue.identifier}, cannot transition")
            return

        # Fetch comments and parse tracking to get workflow from tracking comment
        client = self._ensure_tracker_client()
        comments = await self._load_issue_comments(client, issue)
        tracking = parse_latest_tracking(comments)

        # Resolve workflow for this issue (using tracking to get stored workflow)
        workflow = await self._resolve_workflow_for_issue(issue, tracking)
        if workflow is None:
            logger.error(f"Cannot transition {issue.identifier}: no workflow found")
            return

        # Use workflow-scoped states
        workflow_states = workflow.states

        current_cfg = workflow_states.get(current_state_name)
        if not current_cfg:
            logger.warning(f"Unknown state '{current_state_name}' for {issue.identifier}")
            return

        target_name = current_cfg.transitions.get(transition_name)
        if not target_name:
            logger.warning(
                f"No '{transition_name}' transition from state '{current_state_name}' "
                f"for {issue.identifier}"
            )
            return

        target_cfg = workflow_states.get(target_name)
        if not target_cfg:
            logger.warning(f"Transition target '{target_name}' not found in config")
            return

        run = self._issue_state_runs.get(issue.id, 1)

        if target_cfg.type == "terminal":
            # Move issue to terminal state
            terminal_state = (
                self.cfg.terminal_linear_states()[0]
                if self.cfg.terminal_linear_states()
                else "Done"
            )
            try:
                client = self._ensure_tracker_client()
                moved = await client.update_issue_state(issue.id, terminal_state)
                if moved:
                    logger.info(f"Moved {issue.identifier} to terminal state '{terminal_state}'")
                else:
                    logger.warning(
                        f"Failed to move {issue.identifier} to terminal state '{terminal_state}'"
                    )
            except Exception as e:
                logger.warning(f"Failed to move {issue.identifier} to terminal: {e}")
            # Clean up workspace
            try:
                ws_root = self.cfg.workspace.resolved_root()
                await remove_workspace(ws_root, issue.identifier, self.cfg.hooks)
            except Exception as e:
                logger.warning(f"Failed to remove workspace for {issue.identifier}: {e}")
            # Clean up tracking state
            self._issue_current_state.pop(issue.id, None)
            self._issue_state_runs.pop(issue.id, None)
            self._pending_gates.pop(issue.id, None)
            self._last_session_ids.pop(issue.id, None)
            self._last_prompt_stage_by_issue.pop(issue.id, None)
            self._issue_workflow_cache.pop(issue.id, None)  # Clear workflow cache
            self._issue_input_tokens.pop(issue.id, None)
            self._issue_output_tokens.pop(issue.id, None)
            self._issue_total_tokens.pop(issue.id, None)
            self.claimed.discard(issue.id)
            self.completed.add(issue.id)

        elif target_cfg.type == "gate":
            self._issue_current_state[issue.id] = target_name
            await self._enter_gate(issue, target_name, workflow.name)

        else:
            # Agent state — post state comment, ensure active Linear state, schedule retry
            self._issue_current_state[issue.id] = target_name
            client = self._ensure_tracker_client()
            comment = make_state_comment(
                state=target_name,
                run=run,
                workflow=workflow.name,
            )
            await client.post_comment(issue.id, comment)

            # Ensure issue is in active Linear state
            active_state = self.cfg.linear_states.active
            moved = await client.update_issue_state(issue.id, active_state)
            if not moved:
                logger.warning(
                    f"Failed to move {issue.identifier} to active state '{active_state}'"
                )

            self._schedule_retry(issue, attempt_num=0, delay_ms=1000)

    async def _handle_gate_responses(self):
        """Check for gate-approved and rework issues, handle transitions."""
        # Early return if no gate states in any workflow
        has_gates = any(sc.type == "gate" for sc in self.cfg.states.values())
        has_gates = has_gates or any(
            sc.type == "gate" for wf in self.cfg.workflows.values() for sc in wf.states.values()
        )
        if not has_gates:
            return

        client = self._ensure_tracker_client()

        # Fetch gate-approved issues
        try:
            approved_issues = await client.fetch_issues_by_states(
                self.cfg.resolved_project_slug(),
                [self.cfg.linear_states.gate_approved],
            )
        except Exception as e:
            logger.warning(f"Failed to fetch gate-approved issues: {e}")
            approved_issues = []

        for issue in approved_issues:
            if issue.id in self.running or issue.id in self.claimed:
                continue

            try:
                comments = await self._load_issue_comments(client, issue)
            except CommentsFetchError as e:
                logger.warning(
                    "Skipping %s this tick: could not load comments for gate approval: %s",
                    issue.identifier,
                    e,
                )
                continue
            gate_waiting = parse_latest_gate_waiting(comments)
            gate_state = self._pending_gates.pop(issue.id, None)
            if not gate_state and gate_waiting:
                gate_state = str(gate_waiting.get("state") or "")

            tracking_for_resolve = gate_waiting or parse_latest_tracking(comments)

            if gate_state:
                # Resolve workflow for this issue (using tracking to get stored workflow)
                workflow = await self._resolve_workflow_for_issue(issue, tracking_for_resolve)
                if workflow is None:
                    logger.error(
                        f"Cannot handle gate approval for {issue.identifier}: no workflow found"
                    )
                    # Issue is orphaned - move to terminal state to prevent stuck state
                    await self._handle_orphaned_issue(
                        issue, "gate approval", release_agent_resources=True
                    )
                    continue
                workflow_states = workflow.states

                gate_cfg = workflow_states.get(gate_state)
                if not gate_cfg or "approve" not in gate_cfg.transitions:
                    logger.error(
                        f"Gate-approved issue {issue.identifier}: gate '{gate_state}' "
                        f"has no approve transition in workflow"
                    )
                    await self._handle_orphaned_issue(
                        issue,
                        "gate approval (invalid gate configuration)",
                        release_agent_resources=True,
                    )
                    continue
                target = gate_cfg.transitions["approve"]
                if target not in workflow_states:
                    logger.error(
                        f"Gate '{gate_state}' approve transition points to unknown state '{target}'"
                    )
                    await self._handle_orphaned_issue(
                        issue,
                        "gate approval (invalid approve transition target)",
                        release_agent_resources=True,
                    )
                    continue

                run = self._issue_state_runs.get(issue.id, 1)
                comment = make_gate_comment(
                    state=gate_state,
                    status="approved",
                    run=run,
                    workflow=workflow.name,
                )
                await client.post_comment(issue.id, comment)

                self._issue_current_state[issue.id] = target

                active_state = self.cfg.linear_states.active
                moved = await client.update_issue_state(issue.id, active_state)
                if moved:
                    issue.state = active_state
                else:
                    logger.warning(
                        f"Failed to move {issue.identifier} to active after gate approval"
                    )
                self._last_issues[issue.id] = issue
                logger.info(
                    f"Gate approved issue={issue.identifier} gate={gate_state} workflow={workflow.name}"
                )
            else:
                logger.warning(
                    f"Gate-approved issue {issue.identifier} in '{self.cfg.linear_states.gate_approved}' "
                    f"but gate state could not be recovered; orphaning"
                )
                await self._handle_orphaned_issue(
                    issue,
                    "gate approval (gate state could not be recovered)",
                    release_agent_resources=True,
                )

        # Fetch rework issues
        try:
            rework_issues = await client.fetch_issues_by_states(
                self.cfg.resolved_project_slug(),
                [self.cfg.linear_states.rework],
            )
        except Exception as e:
            logger.warning(f"Failed to fetch rework issues: {e}")
            rework_issues = []

        for issue in rework_issues:
            if issue.id in self.running or issue.id in self.claimed:
                continue

            try:
                comments = await self._load_issue_comments(client, issue)
            except CommentsFetchError as e:
                logger.warning(
                    "Skipping %s this tick: could not load comments for rework handling: %s",
                    issue.identifier,
                    e,
                )
                continue
            gate_waiting = parse_latest_gate_waiting(comments)
            gate_state = self._pending_gates.pop(issue.id, None)
            if not gate_state and gate_waiting:
                gate_state = str(gate_waiting.get("state") or "")

            tracking_for_resolve = gate_waiting or parse_latest_tracking(comments)

            if gate_state:
                # Resolve workflow for this issue (using tracking to get stored workflow)
                workflow = await self._resolve_workflow_for_issue(issue, tracking_for_resolve)
                if workflow is None:
                    logger.error(f"Cannot handle rework for {issue.identifier}: no workflow found")
                    # Issue is orphaned - move to terminal state to prevent stuck state
                    await self._handle_orphaned_issue(issue, "rework", release_agent_resources=True)
                    continue
                workflow_states = workflow.states

                gate_cfg = workflow_states.get(gate_state)
                rework_to = gate_cfg.rework_to if gate_cfg else ""
                if not rework_to:
                    logger.warning(
                        f"Gate {gate_state} has no rework_to target; orphaning {issue.identifier}"
                    )
                    await self._handle_orphaned_issue(
                        issue,
                        "rework (gate missing rework_to)",
                        release_agent_resources=True,
                    )
                    continue

                # Validate rework_to exists in workflow_states
                if rework_to not in workflow_states:
                    logger.error(
                        f"Gate '{gate_state}' rework_to '{rework_to}' is not a valid state, "
                        f"orphaning {issue.identifier}"
                    )
                    await self._handle_orphaned_issue(
                        issue,
                        "rework (invalid rework_to target)",
                        release_agent_resources=True,
                    )
                    continue

                # Check max_rework
                run = self._issue_state_runs.get(issue.id, 1)
                max_rework = gate_cfg.max_rework if gate_cfg else None
                if max_rework is not None and run >= max_rework:
                    comment = make_gate_comment(
                        state=gate_state,
                        status="escalated",
                        run=run,
                        workflow=workflow.name,
                    )
                    await client.post_comment(issue.id, comment)
                    logger.warning(
                        f"Max rework exceeded issue={issue.identifier} "
                        f"gate={gate_state} run={run} max={max_rework}"
                    )
                    await self._handle_orphaned_issue(
                        issue,
                        "rework (max rework exceeded)",
                        release_agent_resources=True,
                    )
                    continue

                new_run = run + 1
                self._issue_state_runs[issue.id] = new_run

                comment = make_gate_comment(
                    state=gate_state,
                    status="rework",
                    rework_to=rework_to,
                    run=new_run,
                    workflow=workflow.name,
                )
                await client.post_comment(issue.id, comment)

                self._issue_current_state[issue.id] = rework_to

                active_state = self.cfg.linear_states.active
                moved = await client.update_issue_state(issue.id, active_state)
                if moved:
                    issue.state = active_state
                else:
                    logger.warning(f"Failed to move {issue.identifier} to active after rework")
                self._last_issues[issue.id] = issue
                logger.info(
                    f"Rework issue={issue.identifier} gate={gate_state} "
                    f"rework_to={rework_to} run={new_run} workflow={workflow.name}"
                )
            else:
                logger.warning(
                    f"Rework issue {issue.identifier} in '{self.cfg.linear_states.rework}' "
                    f"but gate state could not be recovered; orphaning"
                )
                await self._handle_orphaned_issue(
                    issue,
                    "rework (gate state could not be recovered)",
                    release_agent_resources=True,
                )

    async def _tick(self):
        """Single poll tick: reconcile, validate, fetch, dispatch."""
        # Reload workflow (supports hot-reload)
        errors = self._load_workflow()

        # Part 1: Reconcile running issues
        await self._reconcile()

        # Handle gate responses
        await self._handle_gate_responses()

        # Part 2: Validate config
        if errors:
            logger.warning(f"Config invalid, skipping dispatch: {errors}")
            return

        # Part 3: Fetch candidates
        try:
            client = self._ensure_tracker_client()
            candidates = await client.fetch_candidate_issues(
                self.cfg.resolved_project_slug(),
                self.cfg.active_linear_states(),
            )
        except Exception as e:
            logger.error(f"Failed to fetch candidates: {e}")
            return

        # Cache issues for retry lookup
        for issue in candidates:
            self._last_issues[issue.id] = issue

        # Part 4: Sort by priority
        candidates.sort(
            key=lambda i: (
                i.priority if i.priority is not None else 999,
                i.created_at or datetime.min.replace(tzinfo=UTC),
                i.identifier,
            )
        )

        # Resolve state for new issues before dispatch
        for issue in candidates:
            if issue.id not in self._issue_current_state and issue.id not in self.running:
                try:
                    await self._resolve_current_state(issue)
                except Exception as e:
                    logger.warning(f"Failed to resolve state for {issue.identifier}: {e}")

        # Part 5: Dispatch
        available_slots = max(self.cfg.agent.max_concurrent_agents - len(self.running), 0)

        for issue in candidates:
            if available_slots <= 0:
                break
            if not self._is_eligible(issue):
                continue

            # Per-state concurrency check
            state_key = issue.state.strip().lower()
            state_limit = self.cfg.agent.max_concurrent_agents_by_state.get(state_key)
            if state_limit is not None:
                state_count = sum(
                    1
                    for r in self.running.values()
                    if self._last_issues.get(r.issue_id, Issue(id="", identifier="", title=""))
                    .state.strip()
                    .lower()
                    == state_key
                )
                if state_count >= state_limit:
                    continue

            self._dispatch(issue)
            available_slots -= 1

    def _is_eligible(self, issue: Issue) -> bool:
        """Check if an issue is eligible for dispatch."""
        if not issue.id or not issue.identifier or not issue.title or not issue.state:
            return False

        state_lower = issue.state.strip().lower()
        active_lower = [s.strip().lower() for s in self.cfg.active_linear_states()]
        terminal_lower = [s.strip().lower() for s in self.cfg.terminal_linear_states()]

        if state_lower not in active_lower:
            return False
        if state_lower in terminal_lower:
            return False
        if issue.id in self.running:
            return False
        if issue.id in self.claimed:
            return False

        # Blocker check for Todo
        if state_lower == "todo":
            for blocker in issue.blocked_by:
                if blocker.state and blocker.state.strip().lower() not in terminal_lower:
                    return False

        return True

    def _dispatch(
        self, issue: Issue, attempt_num: int | None = None, previous_error: str | None = None
    ):
        """Dispatch a worker for an issue."""
        self.claimed.add(issue.id)

        # Resolve workflow for this issue
        try:
            workflow = self.cfg.get_workflow_for_issue(issue)
        except ValueError as e:
            logger.error(f"Cannot dispatch {issue.identifier}: {e}")
            self.claimed.discard(issue.id)
            return

        workflow_name = workflow.name
        self._issue_workflow_cache[issue.id] = workflow

        state_name = self._issue_current_state.get(issue.id)
        if not state_name:
            state_name = self.cfg.entry_state_for_workflow(workflow)

        state_cfg = workflow.states.get(state_name) if state_name else None

        # If at a gate, enter it instead of dispatching a worker
        if state_name and state_cfg and state_cfg.type == "gate":
            asyncio.create_task(self._safe_enter_gate(issue, state_name, workflow_name))
            return

        attempt = RunAttempt(
            issue_id=issue.id,
            issue_identifier=issue.identifier,
            attempt=attempt_num,
            state_name=state_name,
            workflow_name=workflow_name,
            previous_error=previous_error,
        )

        # Session handling
        use_fresh_session = False
        if state_cfg and state_cfg.session == "fresh":
            use_fresh_session = True

        if not use_fresh_session:
            if issue.id in self.running:
                old = self.running[issue.id]
                if old.session_id:
                    attempt.session_id = old.session_id
            elif issue.id in self._last_session_ids:
                attempt.session_id = self._last_session_ids[issue.id]

        self.running[issue.id] = attempt
        task = asyncio.create_task(self._run_worker(issue, attempt))
        self._tasks[issue.id] = task

        runner = state_cfg.runner if state_cfg else "claude"
        logger.info(
            f"Dispatched issue={issue.identifier} "
            f"workflow={workflow_name} "
            f"state={issue.state} "
            f"machine_state={state_name or 'entry'} "
            f"runner={runner} "
            f"session={'fresh' if use_fresh_session else 'inherit'} "
            f"attempt={attempt_num}"
        )

    async def _run_worker(self, issue: Issue, attempt: RunAttempt):
        """Worker coroutine: prepare workspace, run agent turns."""
        try:
            workflow = self._workflow_for_run_attempt(issue, attempt)
            if workflow is None:
                logger.error(f"Workflow resolution failed for {issue.identifier}")
                attempt.status = "failed"
                attempt.error = f"No workflow matches issue labels: {getattr(issue, 'labels', [])}"
                self._on_worker_exit(issue, attempt)
                return
            workflow_states = workflow.states

            # Resolve state if not set
            if not attempt.state_name:
                state_name, run = await self._resolve_current_state(issue)
                attempt.state_name = state_name
                state_cfg = workflow_states.get(state_name)
                if state_cfg and state_cfg.type == "gate":
                    # Issue should be at a gate, not running
                    await self._enter_gate(issue, state_name, workflow.name)
                    return

            state_name = attempt.state_name
            state_cfg = workflow_states.get(state_name) if state_name else None

            claude_cfg = self.cfg.claude
            hooks_cfg = self.cfg.hooks
            runner_type = "claude"

            if state_cfg:
                claude_cfg, hooks_cfg = merge_state_config(
                    state_cfg, self.cfg.claude, self.cfg.hooks
                )
                runner_type = state_cfg.runner

            ws_root = self.cfg.workspace.resolved_root()
            ws = await ensure_workspace(ws_root, issue.identifier, self.cfg.hooks)
            attempt.workspace_path = str(ws.path)

            # Move issue from Todo to In Progress if needed
            todo_state = self.cfg.linear_states.todo
            if todo_state and issue.state.strip().lower() == todo_state.strip().lower():
                try:
                    client = self._ensure_tracker_client()
                    active_state = self.cfg.linear_states.active
                    moved = await client.update_issue_state(issue.id, active_state)
                    if moved:
                        issue.state = active_state
                        logger.info(
                            f"Moved {issue.identifier} from '{todo_state}' to '{active_state}'"
                        )
                    else:
                        logger.warning(
                            f"Failed to move {issue.identifier} from '{todo_state}' to '{active_state}' "
                            f"— Linear API returned failure"
                        )
                except Exception as e:
                    logger.warning(f"Failed to move {issue.identifier} to active: {e}")

            # Post state tracking comment (only for first dispatch of a state)
            if state_name:
                run = self._issue_state_runs.get(issue.id, 1)
                if run == 1 and (attempt.attempt is None or attempt.attempt == 0):
                    client = self._ensure_tracker_client()
                    comment = make_state_comment(
                        state=state_name,
                        run=run,
                        workflow=workflow.name,
                    )
                    await client.post_comment(issue.id, comment)

            # Run on_stage_enter hook if defined
            if state_cfg and state_cfg.hooks and state_cfg.hooks.on_stage_enter:
                from .workspace import run_hook

                ok = await run_hook(
                    state_cfg.hooks.on_stage_enter,
                    ws.path,
                    (state_cfg.hooks.timeout_ms if state_cfg.hooks else self.cfg.hooks.timeout_ms),
                    f"on_stage_enter:{state_name}",
                )
                if not ok:
                    attempt.status = "failed"
                    attempt.error = f"on_stage_enter hook failed for state {state_name}"
                    self._on_worker_exit(issue, attempt)
                    return

            prompt = await self._render_prompt_async(
                issue,
                attempt.attempt,
                state_name,
                workflow,
                attempt.previous_error,
                attempt.session_id,
                ws.path,
            )

            # Build env vars for the agent subprocess from workflow.yaml config
            agent_env = self.cfg.agent_env()

            # State machine mode: single turn per dispatch. The state
            # machine handles continuation via _transition after each
            # turn completes — multi-turn loops would bypass gate
            # transitions and cause the agent to blow past stage
            # boundaries.
            if state_name and state_cfg:
                attempt = await run_turn(
                    runner_type=runner_type,
                    claude_cfg=claude_cfg,
                    hooks_cfg=hooks_cfg,
                    prompt=prompt,
                    workspace_path=ws.path,
                    issue=issue,
                    attempt=attempt,
                    on_event=self._on_agent_event,
                    on_pid=self._on_child_pid,
                    env=agent_env,
                    log_agent_output_dir=self._log_agent_output_dir,
                )
            else:
                # Legacy mode: multi-turn loop
                max_turns = claude_cfg.max_turns
                for turn in range(max_turns):
                    if turn > 0:
                        current_state = issue.state
                        try:
                            client = self._ensure_tracker_client()
                            states = await client.fetch_issue_states_by_ids([issue.id])
                            current_state = states.get(issue.id, issue.state)
                            state_lower = current_state.strip().lower()
                            active_lower = [
                                s.strip().lower() for s in self.cfg.active_linear_states()
                            ]
                            if state_lower not in active_lower:
                                logger.info(
                                    f"Issue {issue.identifier} no longer active "
                                    f"(state={current_state}), stopping"
                                )
                                break
                        except Exception as e:
                            logger.warning(f"State check failed, continuing: {e}")

                        prompt = (
                            f"Continue working on {issue.identifier}. "
                            f"The issue is still in '{current_state}' state. "
                            f"Check your progress and continue the task."
                        )

                    attempt = await run_turn(
                        runner_type=runner_type,
                        claude_cfg=claude_cfg,
                        hooks_cfg=hooks_cfg,
                        prompt=prompt,
                        workspace_path=ws.path,
                        issue=issue,
                        attempt=attempt,
                        on_event=self._on_agent_event,
                        on_pid=self._on_child_pid,
                        env=agent_env,
                        log_agent_output_dir=self._log_agent_output_dir,
                    )

                    if attempt.status != "succeeded":
                        break

            self._on_worker_exit(issue, attempt)

        except asyncio.CancelledError:
            logger.info(f"Worker cancelled issue={issue.identifier}")
            attempt.status = "canceled"
            self._on_worker_exit(issue, attempt)
        except Exception as e:
            logger.error(f"Worker error issue={issue.identifier}: {e}")
            attempt.status = "failed"
            attempt.error = str(e)
            self._on_worker_exit(issue, attempt)

    async def _render_prompt_async(
        self,
        issue: Issue,
        attempt_num: int | None,
        state_name: str | None = None,
        workflow: WorkflowConfig | None = None,
        previous_error: str | None = None,
        session_id: str | None = None,
        workspace_path: Path | None = None,
    ) -> str:
        """Render prompt using state machine prompt assembly (async — fetches comments)."""
        # Get workflow if not provided
        if workflow is None:
            try:
                workflow = self.cfg.get_workflow_for_issue(issue)
            except ValueError as e:
                logger.error(f"Prompt render failed - no workflow matches {issue.identifier}: {e}")
                raise RuntimeError(
                    f"No workflow configured for issue with labels {getattr(issue, 'labels', [])}"
                ) from e

        workflow_states = workflow.states
        workflow_prompts = workflow.prompts

        if state_name and state_name in workflow_states:
            state_cfg = workflow_states[state_name]
            run = self._issue_state_runs.get(issue.id, 1)
            last_completed = self._last_completed_at.get(issue.id)
            last_run_at = last_completed.isoformat() if last_completed else None
            include_stage_prompt_on_resume = False
            if session_id:
                pending = self._last_prompt_stage_by_issue.get(issue.id)
                include_stage_prompt_on_resume = pending == (session_id, state_name)
                if include_stage_prompt_on_resume:
                    self._last_prompt_stage_by_issue.pop(issue.id, None)

            # Fetch comments for lifecycle context (with image downloads if workspace_path provided)
            comments: list[dict] | None = None
            is_rework = False
            try:
                client = self._ensure_tracker_client()
                comments = await self._load_issue_comments(client, issue, workspace_path)
                tracking = parse_latest_tracking(comments)
                if (
                    tracking
                    and tracking.get("type") == "gate"
                    and tracking.get("status") == "rework"
                ):
                    rework_to = tracking.get("rework_to")
                    if not rework_to:
                        gate_state = tracking.get("state")
                        gate_cfg = workflow_states.get(gate_state) if gate_state else None
                        rework_to = gate_cfg.rework_to if gate_cfg else None
                    is_rework = bool(rework_to and rework_to == state_name)
            except Exception as e:
                logger.warning(f"Failed to fetch comments for prompt: {e}")

            return await assemble_prompt(
                cfg=self.cfg,
                workflow_dir=str(self.workflow_path.parent),
                issue=issue,
                state_name=state_name,
                state_cfg=state_cfg,
                workflow_states=workflow_states,
                workflow_prompts=workflow_prompts,
                run=run,
                is_rework=is_rework,
                is_resumed_session=bool(session_id),
                include_stage_prompt_on_resume=include_stage_prompt_on_resume,
                attempt=attempt_num or 1,
                last_run_at=last_run_at,
                comments=comments,
                previous_error=previous_error,
            )

        # Legacy fallback
        return await self._render_prompt(issue, attempt_num, state_name, workflow)

    async def _render_prompt(
        self,
        issue: Issue,
        attempt_num: int | None,
        state_name: str | None = None,
        workflow: WorkflowConfig | None = None,
    ) -> str:
        """Render the prompt template with issue context (legacy/sync fallback)."""
        assert self.workflow is not None

        # Get workflow if not provided
        if workflow is None:
            try:
                workflow = self.cfg.get_workflow_for_issue(issue)
            except ValueError as e:
                logger.error(f"Prompt render failed - no workflow matches {issue.identifier}: {e}")
                raise RuntimeError(
                    f"No workflow configured for issue with labels {getattr(issue, 'labels', [])}"
                ) from e

        workflow_states = workflow.states
        workflow_prompts = workflow.prompts

        # State machine mode: call assemble_prompt without comments
        if state_name and state_name in workflow_states:
            state_cfg = workflow_states[state_name]
            run = self._issue_state_runs.get(issue.id, 1)
            last_completed = self._last_completed_at.get(issue.id)
            last_run_at = last_completed.isoformat() if last_completed else None

            return await assemble_prompt(
                cfg=self.cfg,
                workflow_dir=str(self.workflow_path.parent),
                issue=issue,
                state_name=state_name,
                state_cfg=state_cfg,
                workflow_states=workflow_states,
                workflow_prompts=workflow_prompts,
                run=run,
                is_rework=False,
                attempt=attempt_num or 1,
                last_run_at=last_run_at,
                comments=None,
            )

        # Legacy mode: use workflow prompt_template with Jinja2
        template_str = self.workflow.prompt_template

        if not template_str:
            return f"You are working on an issue from Linear: {issue.identifier} - {issue.title}"

        last_completed = self._last_completed_at.get(issue.id)
        last_run_at = last_completed.isoformat() if last_completed else ""

        try:
            template = self._jinja.from_string(template_str)
            return template.render(
                issue={
                    "id": issue.id,
                    "identifier": issue.identifier,
                    "title": issue.title,
                    "description": issue.description or "",
                    "priority": issue.priority,
                    "state": issue.state,
                    "branch_name": issue.branch_name,
                    "url": issue.url,
                    "labels": issue.labels,
                    "blocked_by": [
                        {"id": b.id, "identifier": b.identifier, "state": b.state}
                        for b in issue.blocked_by
                    ],
                    "created_at": str(issue.created_at) if issue.created_at else "",
                    "updated_at": str(issue.updated_at) if issue.updated_at else "",
                },
                attempt=attempt_num,
                last_run_at=last_run_at,
                stage=state_name,
            )
        except TemplateSyntaxError as e:
            raise RuntimeError(f"Template syntax error: {e}") from e

    def _on_child_pid(self, pid: int, is_register: bool):
        """Track child claude process PIDs for cleanup on shutdown."""
        if is_register:
            self._child_pids.add(pid)
        else:
            self._child_pids.discard(pid)

    def _on_agent_event(self, identifier: str, event_type: str, event: dict):
        """Callback for agent events."""
        logger.debug(f"Agent event issue={identifier} type={event_type}")

    async def _post_work_report(
        self, issue: Issue, attempt: RunAttempt, state_name: str | None = None
    ) -> None:
        """Extract and post work report after agent completion."""
        if not attempt.full_output:
            return

        workflow = self._workflow_for_run_attempt(issue, attempt)
        if workflow is None:
            client = self._ensure_tracker_client()
            try:
                comments = await self._load_issue_comments(client, issue)
            except CommentsFetchError:
                comments = []
            tracking = parse_latest_tracking(comments)
            workflow = await self._resolve_workflow_for_issue(issue, tracking)

        if workflow is not None:
            workflow_states = workflow.states
        elif self.cfg.workflows:
            workflow_states = {}
        else:
            workflow_states = self.cfg.states

        # Determine if next state is a gate
        is_gate = False
        if state_name and state_name in workflow_states:
            state_cfg = workflow_states[state_name]
            if state_cfg.transitions:
                for target in state_cfg.transitions.values():
                    target_cfg = workflow_states.get(target)
                    if target_cfg and target_cfg.type == "gate":
                        is_gate = True
                        break

        # Extract report from agent output
        report_content = extract_report(attempt.full_output)

        logger.info(
            f"Report extraction for {issue.identifier}: {'found' if report_content else 'not found'} ({len(attempt.full_output)} chars in full_output)"
        )

        if report_content:
            comment = format_report_comment(
                report_content=report_content,
                issue=issue,
                state_name=state_name or "unknown",
                run=attempt.attempt or 1,
                is_gate=is_gate,
            )
        else:
            comment = format_no_report_comment(
                issue=issue,
                state_name=state_name or "unknown",
                run=attempt.attempt or 1,
            )

        # Post to Linear
        try:
            client = self._ensure_tracker_client()
            success = await client.post_comment(issue.id, comment)
            if success:
                logger.info(f"Posted work report for {issue.identifier}")
            else:
                logger.error(f"Failed to post work report for {issue.identifier}")
        except Exception as e:
            logger.error(f"Error posting work report for {issue.identifier}: {e}")

    async def _finalize_agent_gate_turn(
        self,
        issue: Issue,
        attempt: RunAttempt,
        workflow: WorkflowConfig | None,
    ) -> None:
        """Resolve routing from output, post report or routing-error comment, then transition."""
        if not attempt.state_name:
            logger.warning(
                f"Agent-gate finalize skipped for {issue.identifier}: missing state_name"
            )
            self.claimed.discard(issue.id)
            return

        if workflow is not None:
            states = workflow.states
        elif self.cfg.workflows:
            states = {}
        else:
            states = self.cfg.states

        state_cfg = states.get(attempt.state_name)
        if not state_cfg or state_cfg.type != "agent-gate":
            logger.warning(
                f"Agent-gate finalize skipped for {issue.identifier}: "
                f"state {attempt.state_name!r} is not agent-gate in resolved workflow"
            )
            self.claimed.discard(issue.id)
            return

        chosen, route_err = decide_agent_gate_transition(attempt.full_output or "", state_cfg)
        client = self._ensure_tracker_client()

        if route_err:
            try:
                await client.post_comment(issue.id, format_route_error_comment(route_err))
            except Exception as e:
                logger.error(f"Failed to post route error for {issue.identifier}: {e}")
        else:
            workflow_states = states
            target_name = state_cfg.transitions.get(chosen)
            is_gate = False
            if target_name:
                tcfg = workflow_states.get(target_name)
                is_gate = bool(tcfg and tcfg.type == "gate")

            report_content = extract_report(attempt.full_output)
            logger.info(
                f"Agent-gate report for {issue.identifier}: "
                f"{'found' if report_content else 'not found'}"
            )
            try:
                if report_content:
                    comment = format_report_comment(
                        report_content=report_content,
                        issue=issue,
                        state_name=attempt.state_name,
                        run=attempt.attempt or 1,
                        is_gate=is_gate,
                    )
                else:
                    comment = format_no_report_comment(
                        issue=issue,
                        state_name=attempt.state_name or "unknown",
                        run=attempt.attempt or 1,
                    )
                await client.post_comment(issue.id, comment)
            except Exception as e:
                logger.error(f"Error posting agent-gate report for {issue.identifier}: {e}")

        await self._safe_transition(issue, chosen)

    def _on_worker_exit(self, issue: Issue, attempt: RunAttempt):
        """Handle worker completion."""
        self.total_input_tokens += attempt.input_tokens
        self.total_output_tokens += attempt.output_tokens
        self.total_tokens += attempt.total_tokens
        self._issue_input_tokens[issue.id] = (
            self._issue_input_tokens.get(issue.id, 0) + attempt.input_tokens
        )
        self._issue_output_tokens[issue.id] = (
            self._issue_output_tokens.get(issue.id, 0) + attempt.output_tokens
        )
        self._issue_total_tokens[issue.id] = (
            self._issue_total_tokens.get(issue.id, 0) + attempt.total_tokens
        )
        if attempt.started_at:
            elapsed = (datetime.now(UTC) - attempt.started_at).total_seconds()
            self.total_seconds_running += elapsed

        if attempt.session_id:
            self._last_session_ids[issue.id] = attempt.session_id

        completed_at = datetime.now(UTC)
        attempt.completed_at = completed_at
        if attempt.status != "canceled":
            self._last_completed_at[issue.id] = completed_at

        name_undef, name_undef_ctx = self._workflow_name_undefined_in_config(issue, attempt)
        label_mismatch, label_mismatch_ctx = (False, None)
        if not name_undef:
            label_mismatch, label_mismatch_ctx = self._workflow_label_mismatch_after_run(
                issue, attempt
            )

        workflow_for_exit = None if name_undef else self._workflow_for_run_attempt(issue, attempt)

        if workflow_for_exit is not None:
            states_to_check = workflow_for_exit.states
        elif self.cfg.workflows:
            states_to_check = {}
        else:
            states_to_check = self.cfg.states
        st_exit = states_to_check.get(attempt.state_name) if attempt.state_name else None
        workflow_unresolved = workflow_for_exit is None and bool(self.cfg.workflows)
        config_error_ctx: str | None = None
        if name_undef:
            config_error_ctx = name_undef_ctx
        elif label_mismatch and label_mismatch_ctx is not None:
            config_error_ctx = label_mismatch_ctx
        workflow_config_error_exit = config_error_ctx is not None
        agent_gate_finalize = (
            attempt.status == "succeeded"
            and not workflow_unresolved
            and not workflow_config_error_exit
            and st_exit is not None
            and st_exit.type == "agent-gate"
            and attempt.state_name in states_to_check
        )

        # Post work report (async) — agent-gate success uses _finalize_agent_gate_turn instead.
        # Omit for timed_out / stalled: the turn did not finish; we retry and do not post a Work
        # Report to Linear (operators should use logs or --log-agent-output for partial output).
        skip_work_report = (
            workflow_unresolved or workflow_config_error_exit
        ) and attempt.status in (
            "succeeded",
            "failed",
            "timed_out",
            "stalled",
        )
        if (
            attempt.full_output
            and not agent_gate_finalize
            and not skip_work_report
            and attempt.status not in ("timed_out", "stalled")
        ):
            asyncio.create_task(self._post_work_report(issue, attempt, attempt.state_name))

        self.running.pop(issue.id, None)
        self._tasks.pop(issue.id, None)
        if attempt.status == "canceled":
            self._last_prompt_stage_by_issue.pop(issue.id, None)

        if attempt.status == "succeeded":
            if workflow_config_error_exit:
                assert config_error_ctx is not None
                logger.warning(
                    f"Workflow config error after worker exit for {issue.identifier}: "
                    f"{config_error_ctx}"
                )
                asyncio.create_task(self._safe_orphan_from_worker_exit(issue, config_error_ctx))
            elif workflow_unresolved:
                logger.warning(
                    f"Workflow unresolved after worker exit for {issue.identifier} "
                    f"(workflow_name={attempt.workflow_name!r}); moving issue to terminal"
                )
                asyncio.create_task(
                    self._safe_orphan_from_worker_exit(
                        issue,
                        "worker exit (workflow could not be resolved)",
                    )
                )
            # Check if state exists in workflow-scoped states (or root states for legacy)
            elif attempt.state_name and attempt.state_name in states_to_check:
                if agent_gate_finalize:
                    asyncio.create_task(
                        self._finalize_agent_gate_turn(issue, attempt, workflow_for_exit)
                    )
                else:
                    # State machine mode: transition via "complete"
                    asyncio.create_task(self._safe_transition(issue, "complete"))
            else:
                # Legacy mode
                self._schedule_retry(issue, attempt_num=1, delay_ms=1000)
        elif attempt.status in ("failed", "timed_out", "stalled"):
            if workflow_config_error_exit:
                assert config_error_ctx is not None
                logger.warning(
                    f"Workflow config error after {attempt.status} for {issue.identifier}: "
                    f"{config_error_ctx}"
                )
                asyncio.create_task(self._safe_orphan_from_worker_exit(issue, config_error_ctx))
            elif workflow_unresolved:
                logger.warning(
                    f"Workflow unresolved after {attempt.status} for {issue.identifier} "
                    f"(workflow_name={attempt.workflow_name!r}); moving issue to terminal"
                )
                asyncio.create_task(
                    self._safe_orphan_from_worker_exit(
                        issue,
                        "worker exit after agent failure (workflow could not be resolved)",
                    )
                )
            else:
                current_attempt = (attempt.attempt or 0) + 1
                delay = min(
                    10_000 * (2 ** (current_attempt - 1)),
                    self.cfg.agent.max_retry_backoff_ms,
                )
                self._schedule_retry(
                    issue,
                    attempt_num=current_attempt,
                    delay_ms=delay,
                    error=attempt.error,
                )
        else:
            self.claimed.discard(issue.id)

    def _schedule_retry(
        self,
        issue: Issue,
        attempt_num: int,
        delay_ms: int,
        error: str | None = None,
    ):
        """Schedule a retry for an issue."""
        # Cancel existing retry
        if issue.id in self._retry_timers:
            self._retry_timers[issue.id].cancel()

        entry = RetryEntry(
            issue_id=issue.id,
            identifier=issue.identifier,
            attempt=attempt_num,
            due_at_ms=time.monotonic() * 1000 + delay_ms,
            error=error,
        )
        self.retry_attempts[issue.id] = entry

        loop = asyncio.get_running_loop()
        handle = loop.call_later(
            delay_ms / 1000,
            lambda: loop.create_task(self._handle_retry(issue.id)),
        )
        self._retry_timers[issue.id] = handle

        logger.info(
            f"Retry scheduled issue={issue.identifier} "
            f"attempt={attempt_num} delay={delay_ms}ms "
            f"error={error or 'continuation'}"
        )

    async def _handle_retry(self, issue_id: str):
        """Handle a retry timer firing."""
        entry = self.retry_attempts.pop(issue_id, None)
        self._retry_timers.pop(issue_id, None)

        if entry is None:
            return

        # Fetch fresh candidates to check eligibility
        try:
            client = self._ensure_tracker_client()
            candidates = await client.fetch_candidate_issues(
                self.cfg.resolved_project_slug(),
                self.cfg.active_linear_states(),
            )
        except Exception as e:
            logger.warning(f"Retry candidate fetch failed: {e}")
            self.claimed.discard(issue_id)
            return

        issue = None
        for c in candidates:
            if c.id == issue_id:
                issue = c
                break

        if issue is None:
            # No longer active
            self.claimed.discard(issue_id)
            logger.info(f"Retry: issue {entry.identifier} no longer active, releasing")
            return

        # Check slots
        available = max(self.cfg.agent.max_concurrent_agents - len(self.running), 0)
        if available <= 0:
            # Re-queue
            self._schedule_retry(
                issue,
                attempt_num=entry.attempt,
                delay_ms=10_000,
                error="no available orchestrator slots",
            )
            return

        self._dispatch(issue, attempt_num=entry.attempt, previous_error=entry.error)

    async def _reconcile(self):
        """Reconcile running issues against current Linear state."""
        if not self.running:
            return

        running_ids = list(self.running.keys())

        try:
            client = self._ensure_tracker_client()
            states = await client.fetch_issue_states_by_ids(running_ids)
        except Exception as e:
            logger.warning(f"Reconciliation state fetch failed: {e}")
            return

        terminal_lower = [s.strip().lower() for s in self.cfg.terminal_linear_states()]
        active_lower = [s.strip().lower() for s in self.cfg.active_linear_states()]
        review_lower = self.cfg.linear_states.review.strip().lower()

        for issue_id in running_ids:
            current_state = states.get(issue_id)
            if current_state is None:
                continue

            state_lower = current_state.strip().lower()

            if state_lower in terminal_lower:
                # Terminal - stop worker and clean workspace
                logger.info(f"Reconciliation: {issue_id} is terminal ({current_state}), stopping")
                task = self._tasks.get(issue_id)
                if task:
                    task.cancel()

                attempt = self.running.get(issue_id)
                if attempt:
                    ws_root = self.cfg.workspace.resolved_root()
                    await remove_workspace(ws_root, attempt.issue_identifier, self.cfg.hooks)

                self.running.pop(issue_id, None)
                self._tasks.pop(issue_id, None)
                self.claimed.discard(issue_id)
                self._issue_workflow_cache.pop(issue_id, None)  # Clear workflow cache
                self._issue_input_tokens.pop(issue_id, None)
                self._issue_output_tokens.pop(issue_id, None)
                self._issue_total_tokens.pop(issue_id, None)

            elif state_lower == review_lower:
                # In review/gate state — stop worker but keep gate tracking
                task = self._tasks.get(issue_id)
                if task:
                    task.cancel()
                self.running.pop(issue_id, None)
                self._tasks.pop(issue_id, None)
                # Note: Keep workflow cache for gate handling

            elif state_lower not in active_lower:
                # Neither active nor terminal nor review - stop without cleanup
                logger.info(f"Reconciliation: {issue_id} not active ({current_state}), stopping")
                task = self._tasks.get(issue_id)
                if task:
                    task.cancel()
                self.running.pop(issue_id, None)
                self._tasks.pop(issue_id, None)
                self.claimed.discard(issue_id)
                self._issue_workflow_cache.pop(issue_id, None)  # Clear workflow cache

    def _get_issue_tokens(self, issue_id: str) -> dict[str, int]:
        """Return per-issue cumulative tokens with a one-month visibility window."""
        last_completed = self._last_completed_at.get(issue_id)
        if last_completed:
            month_ago = datetime.now(UTC) - timedelta(days=31)
            if last_completed < month_ago:
                return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        return {
            "input_tokens": self._issue_input_tokens.get(issue_id, 0),
            "output_tokens": self._issue_output_tokens.get(issue_id, 0),
            "total_tokens": self._issue_total_tokens.get(issue_id, 0),
        }

    def get_state_snapshot(self) -> dict[str, Any]:
        """Get current runtime state for observability."""
        now = datetime.now(UTC)
        active_seconds = sum(
            (now - r.started_at).total_seconds() for r in self.running.values() if r.started_at
        )

        return {
            "generated_at": now.isoformat(),
            "counts": {
                "running": len(self.running),
                "retrying": len(self.retry_attempts),
                "gates": len(self._pending_gates),
            },
            "running": [
                {
                    "issue_id": r.issue_id,
                    "issue_identifier": r.issue_identifier,
                    "workflow_name": r.workflow_name,
                    "session_id": r.session_id,
                    "run": self._issue_state_runs.get(r.issue_id, 1),
                    "turn_count": r.turn_count,
                    "status": r.status,
                    "last_event": r.last_event,
                    "last_message": r.last_message,
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                    "last_event_at": (r.last_event_at.isoformat() if r.last_event_at else None),
                    "tokens": self._get_issue_tokens(r.issue_id),
                    "state_name": r.state_name,
                }
                for r in self.running.values()
            ],
            "retrying": [
                {
                    "issue_id": e.issue_id,
                    "issue_identifier": e.identifier,
                    "attempt": e.attempt,
                    "error": e.error,
                    "run": self._issue_state_runs.get(e.issue_id, 1),
                    "tokens": self._get_issue_tokens(e.issue_id),
                }
                for e in self.retry_attempts.values()
            ],
            "gates": [
                {
                    "issue_id": issue_id,
                    "issue_identifier": self._last_issues.get(
                        issue_id, Issue(id="", identifier=issue_id, title="")
                    ).identifier,
                    "gate_state": gate_state,
                    "run": self._issue_state_runs.get(issue_id, 1),
                    "tokens": self._get_issue_tokens(issue_id),
                }
                for issue_id, gate_state in self._pending_gates.items()
            ],
            "totals": {
                "input_tokens": self.total_input_tokens,
                "output_tokens": self.total_output_tokens,
                "total_tokens": self.total_tokens,
                "seconds_running": round(self.total_seconds_running + active_seconds, 1),
            },
        }
