"""Tests for optional Claude runner full-output file logging."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from stokowski.models import Issue, RunAttempt
from stokowski.runner import (
    _maybe_log_claude_agent_output,
    write_claude_agent_output_log,
)


def test_write_claude_agent_output_log_writes_file_and_content(tmp_path: Path) -> None:
    body = '{"type":"result","result":"hello"}\n'
    fixed = datetime(2026, 4, 10, 12, 0, 0, 123456, tzinfo=UTC)
    path = write_claude_agent_output_log(
        tmp_path,
        issue_identifier="MAN-14",
        state_name="review-findings-route",
        run_num=2,
        turn_count=3,
        full_output=body,
        at=fixed,
    )
    assert path.parent == tmp_path
    assert path.read_text(encoding="utf-8") == body
    assert "MAN-14" in path.name
    assert "review-findings-route" in path.name
    assert "run2" in path.name
    assert "turn3" in path.name
    assert "20260410T120000_123456" in path.name
    assert path.suffix == ".log"


def test_write_claude_agent_output_log_sanitizes_unsafe_filename_parts(tmp_path: Path) -> None:
    fixed = datetime(2026, 1, 1, 0, 0, 0, 0, tzinfo=UTC)
    path = write_claude_agent_output_log(
        tmp_path,
        issue_identifier="TEAM/FOO-1",
        state_name="state:with*bad",
        run_num=1,
        turn_count=1,
        full_output="x",
        at=fixed,
    )
    assert "/" not in path.name
    assert ":" not in path.name
    assert "*" not in path.name
    assert path.read_text(encoding="utf-8") == "x"


def test_write_claude_agent_output_log_creates_parent_directory(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b"
    fixed = datetime(2026, 1, 1, 0, 0, 0, 0, tzinfo=UTC)
    path = write_claude_agent_output_log(
        nested,
        issue_identifier="X-1",
        state_name="s",
        run_num=1,
        turn_count=1,
        full_output="",
        at=fixed,
    )
    assert nested.is_dir()
    assert path.exists()


def test_write_claude_agent_output_log_state_name_none_uses_unknown(tmp_path: Path) -> None:
    fixed = datetime(2026, 6, 15, 8, 30, 0, 0, tzinfo=UTC)
    path = write_claude_agent_output_log(
        tmp_path,
        issue_identifier="I-1",
        state_name=None,
        run_num=1,
        turn_count=1,
        full_output="z",
        at=fixed,
    )
    assert "unknown" in path.name
    assert path.read_text(encoding="utf-8") == "z"


def test_maybe_log_skips_when_log_dir_none(tmp_path: Path) -> None:
    issue = Issue(id="1", identifier="X", title="t")
    attempt = RunAttempt(
        issue_id="1",
        issue_identifier="X",
        full_output="data",
        state_name="s",
        attempt=1,
        turn_count=1,
    )
    _maybe_log_claude_agent_output(None, issue, attempt)
    assert not list(tmp_path.iterdir())


def test_maybe_log_writes_and_logs_info(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    issue = Issue(id="1", identifier="X", title="t")
    attempt = RunAttempt(
        issue_id="1",
        issue_identifier="X",
        full_output="hello",
        state_name="state-a",
        attempt=2,
        turn_count=3,
    )
    with caplog.at_level(logging.INFO):
        _maybe_log_claude_agent_output(tmp_path, issue, attempt)
    paths = list(tmp_path.glob("*.log"))
    assert len(paths) == 1
    assert paths[0].read_text(encoding="utf-8") == "hello"
    assert any("written to" in r.message for r in caplog.records)
    assert any("X" in r.message for r in caplog.records)


def test_maybe_log_oserror_does_not_propagate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(*_args: object, **_kwargs: object) -> Path:
        raise OSError("simulated disk error")

    monkeypatch.setattr("stokowski.runner.write_claude_agent_output_log", boom)
    issue = Issue(id="1", identifier="X", title="t")
    attempt = RunAttempt(
        issue_id="1",
        issue_identifier="X",
        full_output="hi",
        state_name="s",
        attempt=1,
        turn_count=1,
    )
    with caplog.at_level(logging.WARNING):
        _maybe_log_claude_agent_output(tmp_path, issue, attempt)
    assert any("agent output log" in r.message.lower() for r in caplog.records)


def test_maybe_log_attempt_none_uses_run1_in_filename(tmp_path: Path) -> None:
    issue = Issue(id="1", identifier="ZED", title="t")
    attempt = RunAttempt(
        issue_id="1",
        issue_identifier="ZED",
        full_output="x",
        state_name="s",
        attempt=None,
        turn_count=1,
    )
    _maybe_log_claude_agent_output(tmp_path, issue, attempt)
    names = [p.name for p in tmp_path.glob("*.log")]
    assert len(names) == 1
    assert "run1" in names[0]
