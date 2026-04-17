"""CLI parsing and startup invariants (regression guards for main.py)."""

from __future__ import annotations

import contextlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stokowski.main import build_arg_parser
from stokowski.orchestrator import Orchestrator

MINIMAL_WORKFLOW = """
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
        linear_state: active
        transitions:
          complete: done
      done:
        type: terminal
        linear_state: terminal
"""


def test_cli_path_after_log_agent_output_is_log_dir_not_workflow():
    """Regression: `stokowski -v --log-agent-output foo.yaml` binds foo.yaml to the flag, not workflow."""
    p = build_arg_parser()
    args = p.parse_args(["-v", "--log-agent-output", ".stokowski/workflow.yaml"])
    assert args.workflow is None
    assert args.log_agent_output == ".stokowski/workflow.yaml"


def test_cli_workflow_before_log_flag():
    p = build_arg_parser()
    args = p.parse_args(["-v", "proj/w.yaml", "--log-agent-output"])
    assert args.workflow == "proj/w.yaml"
    assert args.log_agent_output == ""


def test_cli_double_dash_workflow_after_log_flag():
    p = build_arg_parser()
    args = p.parse_args(["-v", "--log-agent-output", "--", "proj/w.yaml"])
    assert args.workflow == "proj/w.yaml"
    assert args.log_agent_output == ""


def test_orchestrator_cfg_unavailable_until_workflow_loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Orchestrator.cfg requires _load_workflow(); documents the startup contract."""
    monkeypatch.setenv("LINEAR_API_KEY", "lin_test_dummy_key_for_unit_tests")

    wf = tmp_path / "workflow.yaml"
    wf.write_text(MINIMAL_WORKFLOW)
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "g.md").write_text("g")
    (prompts / "w.md").write_text("w")

    orch = Orchestrator(wf)
    with pytest.raises(AssertionError):
        _ = orch.cfg

    errors = orch._load_workflow()
    assert errors == []
    assert orch.cfg.tracker.project_slug == "test-project"


@pytest.mark.asyncio
async def test_run_orchestrator_loads_workflow_before_using_cfg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Regression: run_orchestrator must not touch orch.cfg before _load_workflow()."""
    monkeypatch.setenv("LINEAR_API_KEY", "lin_test_dummy_key_for_unit_tests")

    wf = tmp_path / "workflow.yaml"
    wf.write_text(MINIMAL_WORKFLOW)
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "g.md").write_text("g")
    (prompts / "w.md").write_text("w")

    from stokowski import main

    @contextlib.contextmanager
    def _fake_live(*_a, **_kw):
        yield MagicMock()

    class _FakeKB:
        def __init__(self, *_a, **_kw):
            pass

        def start(self):
            pass

        def stop(self):
            pass

    with (
        patch.object(main, "check_for_updates", new_callable=AsyncMock),
        patch.object(main, "KeyboardHandler", _FakeKB),
        patch.object(main, "Live", _fake_live),
        patch.object(Orchestrator, "start", new_callable=AsyncMock) as start_mock,
    ):
        await main.run_orchestrator(str(wf), port=None, log_agent_output_dir=None)

    start_mock.assert_awaited_once()
