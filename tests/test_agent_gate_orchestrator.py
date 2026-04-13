"""Orchestrator behaviour for agent-gate states."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stokowski.config import parse_workflow_file
from stokowski.linear import CommentsFetchResult
from stokowski.models import Issue, RunAttempt
from stokowski.orchestrator import Orchestrator
from stokowski.tracking import make_gate_comment, make_state_comment


def _assert_single_await(mock: AsyncMock):
    """Narrow AsyncMock.await_args for pyright (await_args may be typed as optional)."""
    mock.assert_awaited_once()
    call = mock.await_args
    assert call is not None
    return call


AG_GATE_YAML = """
tracker:
  project_slug: test-project

workflows:
  default:
    default: true
    prompts:
      global_prompt: prompts/g.md
    states:
      start:
        type: agent
        prompt: prompts/start.md
        transitions:
          complete: route
      route:
        type: agent-gate
        prompt: prompts/route.md
        default_transition: to_human
        transitions:
          pick_fix: fix
          to_human: human
      fix:
        type: agent
        prompt: prompts/fix.md
        transitions:
          complete: route
      human:
        type: gate
        linear_state: review
        rework_to: start
        transitions:
          approve: done
      done:
        type: terminal
"""

AG_ONLY_YAML = """
tracker:
  project_slug: test-project

workflows:
  default:
    default: true
    prompts:
      global_prompt: prompts/g.md
    states:
      work:
        type: agent
        prompt: prompts/w.md
        transitions:
          complete: done
      done:
        type: terminal
"""

ROUTE_OK = """<<<STOKOWSKI_ROUTE>>>
{"transition": "pick_fix"}
<<<END_STOKOWSKI_ROUTE>>>
<stokowski:report>
## Summary
ok
</stokowski:report>
"""


def _orch(tmp_path, content: str) -> Orchestrator:
    wf_file = tmp_path / "workflow.yaml"
    wf_file.write_text(content)
    o = Orchestrator(wf_file)
    o.workflow = parse_workflow_file(wf_file)
    return o


def _issue() -> Issue:
    return Issue(
        id="i1",
        identifier="T-1",
        title="t",
        state="In Progress",
        labels=[],
    )


@pytest.mark.asyncio
async def test_render_prompt_async_catches_non_comment_fetch_errors_and_omits_comments(
    tmp_path,
):
    """Regression: broad except so bugs in client setup do not kill the worker."""
    orch = _orch(tmp_path, AG_GATE_YAML)
    issue = _issue()
    captured: dict[str, object] = {}

    def capture_assemble(*_a, **kw):
        captured["comments"] = kw.get("comments")
        return "ok-prompt"

    with (
        patch.object(orch, "_load_issue_comments", side_effect=RuntimeError("boom")),
        patch("stokowski.orchestrator.assemble_prompt", side_effect=capture_assemble),
    ):
        out = await orch._render_prompt_async(issue, 1, "start", orch.cfg.workflows["default"])

    assert out == "ok-prompt"
    assert captured.get("comments") is None


@pytest.mark.asyncio
async def test_agent_gate_success_transitions_chosen_key_and_posts_report(tmp_path):
    orch = _orch(tmp_path, AG_GATE_YAML)
    issue = _issue()
    orch._issue_workflow_cache[issue.id] = orch.cfg.get_workflow_for_issue(issue)
    orch._issue_current_state[issue.id] = "route"

    attempt = RunAttempt(
        issue_id=issue.id,
        issue_identifier=issue.identifier,
        status="succeeded",
        state_name="route",
        full_output=ROUTE_OK,
    )

    mock_client = MagicMock()
    mock_client.post_comment = AsyncMock(return_value=True)
    mock_safe = AsyncMock()

    bg_tasks: list[asyncio.Task[None]] = []
    real_create_task = asyncio.create_task

    def capture_create_task(coro):  # type: ignore[no-untyped-def]
        t = real_create_task(coro)
        bg_tasks.append(t)
        return t

    with (
        patch.object(orch, "_ensure_linear_client", return_value=mock_client),
        patch.object(orch, "_safe_transition", mock_safe),
        patch("stokowski.orchestrator.asyncio.create_task", side_effect=capture_create_task),
    ):
        orch._on_worker_exit(issue, attempt)
        await asyncio.gather(*bg_tasks)

    mock_safe.assert_awaited_once_with(issue, "pick_fix")
    assert mock_client.post_comment.await_count == 1
    bodies = [
        str(c.kwargs.get("body") or c.args[1]) for c in mock_client.post_comment.await_args_list
    ]
    assert any("stokowski:report" in b for b in bodies)
    assert not any("route-error" in b for b in bodies)


@pytest.mark.asyncio
async def test_agent_gate_routing_error_posts_fallback_and_error_comment(tmp_path):
    orch = _orch(tmp_path, AG_GATE_YAML)
    issue = _issue()
    orch._issue_workflow_cache[issue.id] = orch.cfg.get_workflow_for_issue(issue)
    orch._issue_current_state[issue.id] = "route"

    attempt = RunAttempt(
        issue_id=issue.id,
        issue_identifier=issue.identifier,
        status="succeeded",
        state_name="route",
        full_output="no routing markers at all",
    )

    mock_client = MagicMock()
    mock_client.post_comment = AsyncMock(return_value=True)
    mock_safe = AsyncMock()

    bg_tasks: list[asyncio.Task[None]] = []
    real_create_task = asyncio.create_task

    def capture_create_task(coro):  # type: ignore[no-untyped-def]
        t = real_create_task(coro)
        bg_tasks.append(t)
        return t

    with (
        patch.object(orch, "_ensure_linear_client", return_value=mock_client),
        patch.object(orch, "_safe_transition", mock_safe),
        patch("stokowski.orchestrator.asyncio.create_task", side_effect=capture_create_task),
    ):
        orch._on_worker_exit(issue, attempt)
        await asyncio.gather(*bg_tasks)

    mock_safe.assert_awaited_once_with(issue, "to_human")
    assert mock_client.post_comment.await_count == 1
    bodies = [
        str(c.kwargs.get("body") or c.args[1]) for c in mock_client.post_comment.await_args_list
    ]
    assert any("route-error" in b for b in bodies)
    assert not any("stokowski:report" in b for b in bodies)


@pytest.mark.asyncio
async def test_agent_state_still_complete_and_generic_report(tmp_path):
    orch = _orch(tmp_path, AG_ONLY_YAML)
    issue = _issue()
    orch._issue_workflow_cache[issue.id] = orch.cfg.get_workflow_for_issue(issue)
    orch._issue_current_state[issue.id] = "work"

    attempt = RunAttempt(
        issue_id=issue.id,
        issue_identifier=issue.identifier,
        status="succeeded",
        state_name="work",
        full_output="<stokowski:report>x</stokowski:report>",
    )

    mock_client = MagicMock()
    mock_client.post_comment = AsyncMock(return_value=True)
    mock_client.fetch_comments = AsyncMock(return_value=CommentsFetchResult([], True))
    mock_safe = AsyncMock()

    bg_tasks: list[asyncio.Task[None]] = []
    real_create_task = asyncio.create_task

    def capture_create_task(coro):  # type: ignore[no-untyped-def]
        t = real_create_task(coro)
        bg_tasks.append(t)
        return t

    with (
        patch.object(orch, "_ensure_linear_client", return_value=mock_client),
        patch.object(orch, "_safe_transition", mock_safe),
        patch("stokowski.orchestrator.asyncio.create_task", side_effect=capture_create_task),
    ):
        orch._on_worker_exit(issue, attempt)
        await asyncio.gather(*bg_tasks)

    mock_safe.assert_awaited_once_with(issue, "complete")
    assert mock_client.post_comment.await_count == 1


LEGACY_ROOT_AGENT_GATE_YAML = """
tracker:
  project_slug: test-project

prompts:
  global_prompt: prompts/g.md

states:
  start:
    type: agent
    prompt: prompts/start.md
    transitions:
      complete: route
  route:
    type: agent-gate
    prompt: prompts/route.md
    default_transition: to_human
    transitions:
      pick_fix: fix
      to_human: human
  fix:
    type: agent
    prompt: prompts/fix.md
    transitions:
      complete: route
  human:
    type: gate
    linear_state: review
    rework_to: start
    transitions:
      approve: done
  done:
    type: terminal
"""


@pytest.mark.asyncio
async def test_agent_gate_legacy_root_states_same_as_workflows(tmp_path):
    orch = _orch(tmp_path, LEGACY_ROOT_AGENT_GATE_YAML)
    issue = _issue()
    orch._issue_current_state[issue.id] = "route"

    attempt = RunAttempt(
        issue_id=issue.id,
        issue_identifier=issue.identifier,
        status="succeeded",
        state_name="route",
        workflow_name="default",
        full_output=ROUTE_OK,
    )

    mock_client = MagicMock()
    mock_client.post_comment = AsyncMock(return_value=True)
    mock_safe = AsyncMock()

    bg_tasks: list[asyncio.Task[None]] = []
    real_create_task = asyncio.create_task

    def capture_create_task(coro):  # type: ignore[no-untyped-def]
        t = real_create_task(coro)
        bg_tasks.append(t)
        return t

    with (
        patch.object(orch, "_ensure_linear_client", return_value=mock_client),
        patch.object(orch, "_safe_transition", mock_safe),
        patch("stokowski.orchestrator.asyncio.create_task", side_effect=capture_create_task),
    ):
        orch._on_worker_exit(issue, attempt)
        await asyncio.gather(*bg_tasks)

    mock_safe.assert_awaited_once_with(issue, "pick_fix")
    assert mock_client.post_comment.await_count == 1


@pytest.mark.asyncio
async def test_agent_gate_resolves_workflow_from_attempt_when_cache_empty(tmp_path):
    orch = _orch(tmp_path, AG_GATE_YAML)
    issue = _issue()
    orch._issue_current_state[issue.id] = "route"
    assert issue.id not in orch._issue_workflow_cache

    attempt = RunAttempt(
        issue_id=issue.id,
        issue_identifier=issue.identifier,
        status="succeeded",
        state_name="route",
        workflow_name="default",
        full_output=ROUTE_OK,
    )

    mock_client = MagicMock()
    mock_client.post_comment = AsyncMock(return_value=True)
    mock_safe = AsyncMock()

    bg_tasks: list[asyncio.Task[None]] = []
    real_create_task = asyncio.create_task

    def capture_create_task(coro):  # type: ignore[no-untyped-def]
        t = real_create_task(coro)
        bg_tasks.append(t)
        return t

    with (
        patch.object(orch, "_ensure_linear_client", return_value=mock_client),
        patch.object(orch, "_safe_transition", mock_safe),
        patch("stokowski.orchestrator.asyncio.create_task", side_effect=capture_create_task),
    ):
        orch._on_worker_exit(issue, attempt)
        await asyncio.gather(*bg_tasks)

    mock_safe.assert_awaited_once_with(issue, "pick_fix")
    assert mock_client.post_comment.await_count == 1


TWO_WORKFLOWS_YAML = """
tracker:
  project_slug: test-project

workflows:
  primary:
    label: prim
    prompts:
      global_prompt: prompts/g.md
    states:
      start:
        type: agent
        prompt: prompts/start.md
        transitions:
          complete: route
      route:
        type: agent-gate
        prompt: prompts/route.md
        default_transition: to_human
        transitions:
          to_human: human
      human:
        type: gate
        linear_state: review
        rework_to: start
        transitions:
          approve: done
      done:
        type: terminal
  secondary:
    default: true
    prompts:
      global_prompt: prompts/g.md
    states:
      start:
        type: agent
        prompt: prompts/start.md
        transitions:
          complete: route
      route:
        type: agent-gate
        prompt: prompts/route.md
        default_transition: to_human
        transitions:
          pick_fix: fix
          to_human: human
      fix:
        type: agent
        prompt: prompts/fix.md
        transitions:
          complete: route
      human:
        type: gate
        linear_state: review
        rework_to: start
        transitions:
          approve: done
      done:
        type: terminal
"""


@pytest.mark.asyncio
async def test_get_workflow_for_issue_beats_stale_cache_on_exit(tmp_path):
    """Labels/default workflow from get_workflow_for_issue wins over a stale _issue_workflow_cache."""
    orch = _orch(tmp_path, TWO_WORKFLOWS_YAML)
    issue = _issue()
    orch._issue_current_state[issue.id] = "route"
    orch._issue_workflow_cache[issue.id] = orch.cfg.workflows["primary"]

    attempt = RunAttempt(
        issue_id=issue.id,
        issue_identifier=issue.identifier,
        status="succeeded",
        state_name="route",
        workflow_name="secondary",
        full_output=ROUTE_OK,
    )

    mock_client = MagicMock()
    mock_client.post_comment = AsyncMock(return_value=True)
    mock_safe = AsyncMock()

    bg_tasks: list[asyncio.Task[None]] = []
    real_create_task = asyncio.create_task

    def capture_create_task(coro):  # type: ignore[no-untyped-def]
        t = real_create_task(coro)
        bg_tasks.append(t)
        return t

    with (
        patch.object(orch, "_ensure_linear_client", return_value=mock_client),
        patch.object(orch, "_safe_transition", mock_safe),
        patch("stokowski.orchestrator.asyncio.create_task", side_effect=capture_create_task),
    ):
        orch._on_worker_exit(issue, attempt)
        await asyncio.gather(*bg_tasks)

    # No labels → default workflow is secondary; ROUTE_OK pick_fix is valid there.
    mock_safe.assert_awaited_once_with(issue, "pick_fix")
    assert orch._issue_workflow_cache[issue.id] is orch.cfg.workflows["secondary"]


def test_workflow_label_mismatch_after_run_detects_divergence(tmp_path):
    orch = _orch(tmp_path, TWO_WORKFLOWS_YAML)
    issue = Issue(
        id="i1",
        identifier="T-1",
        title="t",
        state="In Progress",
        labels=["prim"],
    )
    attempt = RunAttempt(
        issue_id=issue.id,
        issue_identifier=issue.identifier,
        workflow_name="secondary",
    )
    bad, ctx = orch._workflow_label_mismatch_after_run(issue, attempt)
    assert bad and ctx
    assert "secondary" in ctx and "primary" in ctx
    assert "label/workflow mismatch" in ctx

    ok_issue = Issue(
        id="i2",
        identifier="T-2",
        title="t",
        state="In Progress",
        labels=[],
    )
    ok_attempt = RunAttempt(
        issue_id=ok_issue.id,
        issue_identifier=ok_issue.identifier,
        workflow_name="secondary",
    )
    assert orch._workflow_label_mismatch_after_run(ok_issue, ok_attempt) == (False, None)


@pytest.mark.asyncio
async def test_worker_exit_label_workflow_mismatch_orphans_config_error_not_transition(tmp_path):
    """Labels map to primary; run was dispatched as secondary → terminal config error, no transition."""
    orch = _orch(tmp_path, TWO_WORKFLOWS_YAML)
    issue = Issue(
        id="i1",
        identifier="T-1",
        title="t",
        state="In Progress",
        labels=["prim"],
    )
    orch._issue_current_state[issue.id] = "route"
    orch._issue_workflow_cache[issue.id] = orch.cfg.workflows["secondary"]

    attempt = RunAttempt(
        issue_id=issue.id,
        issue_identifier=issue.identifier,
        status="succeeded",
        state_name="route",
        workflow_name="secondary",
        full_output=ROUTE_OK,
    )

    mock_client = MagicMock()
    mock_client.post_comment = AsyncMock(return_value=True)
    mock_handle_orphan = AsyncMock()
    mock_safe = AsyncMock()

    bg_tasks: list[asyncio.Task[None]] = []
    real_create_task = asyncio.create_task

    def capture_create_task(coro):  # type: ignore[no-untyped-def]
        t = real_create_task(coro)
        bg_tasks.append(t)
        return t

    with (
        patch.object(orch, "_ensure_linear_client", return_value=mock_client),
        patch.object(orch, "_handle_orphaned_issue", mock_handle_orphan),
        patch.object(orch, "_safe_transition", mock_safe),
        patch("stokowski.orchestrator.asyncio.create_task", side_effect=capture_create_task),
    ):
        orch._on_worker_exit(issue, attempt)
        await asyncio.gather(*bg_tasks)

    call = _assert_single_await(mock_handle_orphan)
    assert "label/workflow mismatch" in call.args[1]
    assert call.kwargs.get("release_agent_resources") is True
    mock_safe.assert_not_called()


def test_workflow_name_undefined_in_config_detected(tmp_path):
    orch = _orch(tmp_path, AG_GATE_YAML)
    issue = _issue()
    attempt = RunAttempt(
        issue_id=issue.id,
        issue_identifier=issue.identifier,
        workflow_name="removed_workflow",
    )
    u, ctx = orch._workflow_name_undefined_in_config(issue, attempt)
    assert u and ctx
    assert "removed_workflow" in ctx
    assert "not defined" in ctx.lower()


@pytest.mark.asyncio
async def test_worker_exit_unknown_workflow_name_orphans_not_label_fallback(tmp_path):
    """Run references a workflow key no longer in YAML → config error, not label-based transition."""
    orch = _orch(tmp_path, AG_GATE_YAML)
    issue = _issue()
    orch._issue_current_state[issue.id] = "route"

    attempt = RunAttempt(
        issue_id=issue.id,
        issue_identifier=issue.identifier,
        status="succeeded",
        state_name="route",
        workflow_name="ghost_workflow",
        full_output=ROUTE_OK,
    )

    mock_client = MagicMock()
    mock_client.post_comment = AsyncMock(return_value=True)
    mock_handle_orphan = AsyncMock()
    mock_safe = AsyncMock()
    mock_wf_for_attempt = MagicMock(wraps=orch._workflow_for_run_attempt)

    bg_tasks: list[asyncio.Task[None]] = []
    real_create_task = asyncio.create_task

    def capture_create_task(coro):  # type: ignore[no-untyped-def]
        t = real_create_task(coro)
        bg_tasks.append(t)
        return t

    with (
        patch.object(orch, "_ensure_linear_client", return_value=mock_client),
        patch.object(orch, "_handle_orphaned_issue", mock_handle_orphan),
        patch.object(orch, "_workflow_for_run_attempt", mock_wf_for_attempt),
        patch.object(orch, "_safe_transition", mock_safe),
        patch("stokowski.orchestrator.asyncio.create_task", side_effect=capture_create_task),
    ):
        orch._on_worker_exit(issue, attempt)
        await asyncio.gather(*bg_tasks)

    mock_wf_for_attempt.assert_not_called()
    call = _assert_single_await(mock_handle_orphan)
    assert "not defined" in call.args[1].lower()
    mock_safe.assert_not_called()


@pytest.mark.asyncio
async def test_handle_gate_responses_missing_gate_state_logs_and_orphans(tmp_path):
    orch = _orch(tmp_path, AG_GATE_YAML)
    issue = Issue(
        id="g1",
        identifier="G-1",
        title="t",
        state="Gate Approved",
        labels=[],
    )
    mock_client = MagicMock()
    mock_client.fetch_issues_by_states = AsyncMock(side_effect=[[issue], []])
    mock_client.fetch_comments = AsyncMock(return_value=CommentsFetchResult([], True))
    mock_handle = AsyncMock()

    with (
        patch.object(orch, "_ensure_linear_client", return_value=mock_client),
        patch.object(orch, "_handle_orphaned_issue", mock_handle),
    ):
        await orch._handle_gate_responses()

    call = _assert_single_await(mock_handle)
    ctx = call.args[1]
    assert "gate state could not be recovered" in ctx.lower()
    assert call.kwargs.get("release_agent_resources") is True


@pytest.mark.asyncio
async def test_handle_gate_responses_uses_last_waiting_gate_not_latest_tracking(tmp_path):
    """When latest tracking is a state comment, still recover gate from last waiting gate."""
    orch = _orch(tmp_path, AG_GATE_YAML)
    issue = Issue(
        id="g1",
        identifier="G-1",
        title="t",
        state="Gate Approved",
        labels=[],
    )
    comments = [
        {"body": make_gate_comment("human", "waiting", workflow="default")},
        {"body": make_state_comment("start", run=2, workflow="default")},
    ]
    mock_client = MagicMock()
    mock_client.fetch_issues_by_states = AsyncMock(side_effect=[[issue], []])
    mock_client.fetch_comments = AsyncMock(return_value=CommentsFetchResult(comments, True))
    mock_client.post_comment = AsyncMock(return_value=True)
    mock_client.update_issue_state = AsyncMock(return_value=True)

    with patch.object(orch, "_ensure_linear_client", return_value=mock_client):
        await orch._handle_gate_responses()

    mock_client.update_issue_state.assert_awaited()
    approved_bodies = [c[0][1] for c in mock_client.post_comment.await_args_list]
    assert any("approved" in b.lower() for b in approved_bodies)


@pytest.mark.asyncio
async def test_handle_gate_approval_invalid_target_orphans_no_approved_tracking(tmp_path):
    orch = _orch(tmp_path, AG_GATE_YAML)
    issue = Issue(
        id="g1",
        identifier="G-1",
        title="t",
        state="Gate Approved",
        labels=[],
    )
    comments = [{"body": make_gate_comment("human", "waiting", workflow="default")}]
    mock_client = MagicMock()
    mock_client.fetch_issues_by_states = AsyncMock(side_effect=[[issue], []])
    mock_client.fetch_comments = AsyncMock(return_value=CommentsFetchResult(comments, True))
    mock_client.post_comment = AsyncMock(return_value=True)
    mock_handle = AsyncMock()

    orch.cfg.workflows["default"].states["human"].transitions = dict(
        orch.cfg.workflows["default"].states["human"].transitions
    )
    orch.cfg.workflows["default"].states["human"].transitions["approve"] = "missing_state"

    with (
        patch.object(orch, "_ensure_linear_client", return_value=mock_client),
        patch.object(orch, "_handle_orphaned_issue", mock_handle),
    ):
        await orch._handle_gate_responses()

    call = _assert_single_await(mock_handle)
    assert "invalid approve" in call.args[1].lower()
    for call in mock_client.post_comment.await_args_list:
        body = call[0][1]
        assert "Gate **human** approved" not in body


@pytest.mark.asyncio
async def test_handle_rework_max_exceeded_orphans(tmp_path):
    yaml = AG_GATE_YAML.replace(
        "rework_to: start\n",
        "rework_to: start\n        max_rework: 2\n",
    )
    orch = _orch(tmp_path, yaml)
    issue = Issue(
        id="r1",
        identifier="R-1",
        title="t",
        state="Rework",
        labels=[],
    )
    orch._issue_state_runs[issue.id] = 2
    comments = [{"body": make_gate_comment("human", "waiting", workflow="default")}]
    mock_client = MagicMock()
    mock_client.fetch_issues_by_states = AsyncMock(side_effect=[[], [issue]])
    mock_client.fetch_comments = AsyncMock(return_value=CommentsFetchResult(comments, True))
    mock_client.post_comment = AsyncMock(return_value=True)
    mock_handle = AsyncMock()

    with (
        patch.object(orch, "_ensure_linear_client", return_value=mock_client),
        patch.object(orch, "_handle_orphaned_issue", mock_handle),
    ):
        await orch._handle_gate_responses()

    call = _assert_single_await(mock_handle)
    assert "max rework exceeded" in call.args[1].lower()
    escalated = [c[0][1] for c in mock_client.post_comment.await_args_list]
    assert any("escalated" in b.lower() or "Max rework" in b for b in escalated)


@pytest.mark.asyncio
async def test_handle_rework_missing_rework_to_orphans(tmp_path):
    orch = _orch(tmp_path, AG_GATE_YAML)
    issue = Issue(
        id="r1",
        identifier="R-1",
        title="t",
        state="Rework",
        labels=[],
    )
    orch.cfg.workflows["default"].states["human"].rework_to = ""
    comments = [{"body": make_gate_comment("human", "waiting", workflow="default")}]
    mock_client = MagicMock()
    mock_client.fetch_issues_by_states = AsyncMock(side_effect=[[], [issue]])
    mock_client.fetch_comments = AsyncMock(return_value=CommentsFetchResult(comments, True))
    mock_handle = AsyncMock()

    with (
        patch.object(orch, "_ensure_linear_client", return_value=mock_client),
        patch.object(orch, "_handle_orphaned_issue", mock_handle),
    ):
        await orch._handle_gate_responses()

    call = _assert_single_await(mock_handle)
    assert "rework_to" in call.args[1].lower()


@pytest.mark.asyncio
async def test_handle_rework_invalid_rework_to_orphans(tmp_path):
    orch = _orch(tmp_path, AG_GATE_YAML)
    issue = Issue(
        id="r1",
        identifier="R-1",
        title="t",
        state="Rework",
        labels=[],
    )
    orch.cfg.workflows["default"].states["human"].rework_to = "ghost"
    comments = [{"body": make_gate_comment("human", "waiting", workflow="default")}]
    mock_client = MagicMock()
    mock_client.fetch_issues_by_states = AsyncMock(side_effect=[[], [issue]])
    mock_client.fetch_comments = AsyncMock(return_value=CommentsFetchResult(comments, True))
    mock_handle = AsyncMock()

    with (
        patch.object(orch, "_ensure_linear_client", return_value=mock_client),
        patch.object(orch, "_handle_orphaned_issue", mock_handle),
    ):
        await orch._handle_gate_responses()

    call = _assert_single_await(mock_handle)
    assert "invalid rework" in call.args[1].lower()


def test_workflow_for_run_attempt_fallback_to_attempt_name_when_get_workflow_fails(tmp_path):
    orch = _orch(tmp_path, AG_GATE_YAML)
    issue = _issue()
    attempt = RunAttempt(
        issue_id=issue.id,
        issue_identifier=issue.identifier,
        workflow_name="default",
    )
    with patch.object(
        orch.cfg,
        "get_workflow_for_issue",
        side_effect=ValueError("no match"),
    ):
        wf = orch._workflow_for_run_attempt(issue, attempt)
    assert wf is orch.cfg.workflows["default"]


@pytest.mark.asyncio
async def test_worker_exit_success_unresolved_workflow_orphans_not_legacy_retry(tmp_path):
    orch = _orch(tmp_path, AG_GATE_YAML)
    issue = _issue()
    orch._issue_current_state[issue.id] = "route"

    attempt = RunAttempt(
        issue_id=issue.id,
        issue_identifier=issue.identifier,
        status="succeeded",
        state_name="route",
        workflow_name="default",
        full_output=ROUTE_OK,
    )

    mock_handle_orphan = AsyncMock()
    mock_schedule = MagicMock()
    mock_client = MagicMock()
    mock_client.post_comment = AsyncMock(return_value=True)

    bg_tasks: list[asyncio.Task[None]] = []
    real_create_task = asyncio.create_task

    def capture_create_task(coro):  # type: ignore[no-untyped-def]
        t = real_create_task(coro)
        bg_tasks.append(t)
        return t

    with (
        patch.object(orch, "_workflow_for_run_attempt", return_value=None),
        patch.object(orch, "_handle_orphaned_issue", mock_handle_orphan),
        patch.object(orch, "_schedule_retry", mock_schedule),
        patch.object(orch, "_ensure_linear_client", return_value=mock_client),
        patch("stokowski.orchestrator.asyncio.create_task", side_effect=capture_create_task),
    ):
        orch._on_worker_exit(issue, attempt)
        await asyncio.gather(*bg_tasks)

    call = _assert_single_await(mock_handle_orphan)
    assert call.args[0] is issue
    assert "worker exit" in call.args[1].lower()
    assert call.kwargs.get("release_agent_resources") is True
    mock_schedule.assert_not_called()


@pytest.mark.asyncio
async def test_worker_exit_failed_unresolved_workflow_orphans_not_retry(tmp_path):
    orch = _orch(tmp_path, AG_GATE_YAML)
    issue = _issue()
    orch._issue_current_state[issue.id] = "route"

    attempt = RunAttempt(
        issue_id=issue.id,
        issue_identifier=issue.identifier,
        status="failed",
        state_name="route",
        workflow_name="default",
        full_output="stderr",
        error="boom",
    )

    mock_handle_orphan = AsyncMock()
    mock_schedule = MagicMock()
    mock_client = MagicMock()
    mock_client.post_comment = AsyncMock(return_value=True)

    bg_tasks: list[asyncio.Task[None]] = []
    real_create_task = asyncio.create_task

    def capture_create_task(coro):  # type: ignore[no-untyped-def]
        t = real_create_task(coro)
        bg_tasks.append(t)
        return t

    with (
        patch.object(orch, "_workflow_for_run_attempt", return_value=None),
        patch.object(orch, "_handle_orphaned_issue", mock_handle_orphan),
        patch.object(orch, "_schedule_retry", mock_schedule),
        patch.object(orch, "_ensure_linear_client", return_value=mock_client),
        patch("stokowski.orchestrator.asyncio.create_task", side_effect=capture_create_task),
    ):
        orch._on_worker_exit(issue, attempt)
        await asyncio.gather(*bg_tasks)

    call = _assert_single_await(mock_handle_orphan)
    assert "after agent failure" in call.args[1].lower()
    assert call.kwargs.get("release_agent_resources") is True
    mock_schedule.assert_not_called()
