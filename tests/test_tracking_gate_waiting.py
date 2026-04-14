"""Tests for recovering the last gate comment with status waiting."""

from __future__ import annotations

from stokowski.tracking import (
    get_last_gate_waiting_timestamp,
    make_gate_comment,
    make_state_comment,
    parse_latest_gate_waiting,
    parse_latest_tracking,
)


def test_parse_latest_gate_waiting_returns_last_waiting_across_comments():
    c1 = {"body": make_gate_comment("g1", "waiting", workflow="default")}
    c2 = {"body": make_state_comment("start", run=1, workflow="default")}
    c3 = {"body": make_gate_comment("g2", "waiting", workflow="default")}
    got = parse_latest_gate_waiting([c1, c2, c3])
    assert got is not None
    assert got.get("type") == "gate"
    assert got.get("state") == "g2"
    assert got.get("status") == "waiting"


def test_parse_latest_gate_waiting_ignores_approved_rework_escalated():
    c1 = {"body": make_gate_comment("human", "waiting", workflow="wf")}
    c2 = {"body": make_gate_comment("human", "approved", workflow="wf")}
    got = parse_latest_gate_waiting([c1, c2])
    assert got is not None
    assert got.get("state") == "human"
    assert got.get("status") == "waiting"


def test_parse_latest_gate_waiting_finds_waiting_when_latest_tracking_is_state():
    """Latest overall tracking may be a state entry; last waiting gate must still be found."""
    c1 = {"body": make_gate_comment("human", "waiting", workflow="default")}
    c2 = {"body": make_state_comment("start", run=2, workflow="default")}
    latest = parse_latest_tracking([c1, c2])
    assert latest is not None
    assert latest["type"] == "state"
    got = parse_latest_gate_waiting([c1, c2])
    assert got is not None
    assert got["state"] == "human"
    assert got["status"] == "waiting"


def test_parse_latest_gate_waiting_none_when_no_waiting():
    c1 = {"body": make_gate_comment("human", "approved", workflow="wf")}
    assert parse_latest_gate_waiting([c1]) is None


def test_parse_latest_gate_waiting_newest_by_payload_timestamp_not_list_order():
    """API may return newest-first; must pick waiting gate with latest JSON timestamp."""
    older = (
        '<!-- stokowski:gate {"state": "research-review", "status": "waiting", '
        '"run": 1, "timestamp": "2026-04-01T10:00:00+00:00", "workflow": "feature"} -->'
    )
    newer = (
        '<!-- stokowski:gate {"state": "merge-review", "status": "waiting", '
        '"run": 2, "timestamp": "2026-04-12T21:20:50.329669+00:00", "workflow": "feature"} -->'
    )
    # Newest-first (wrong for legacy "last in list wins")
    comments = [
        {"body": newer, "createdAt": "2026-04-12T21:20:51.000Z"},
        {"body": older, "createdAt": "2026-04-01T10:00:01.000Z"},
    ]
    got = parse_latest_gate_waiting(comments)
    assert got is not None
    assert got["state"] == "merge-review"
    assert got["status"] == "waiting"


def test_parse_latest_gate_waiting_prefers_created_at_when_payload_timestamp_missing():
    """Fallback when gate JSON has no timestamp: use Linear createdAt."""
    body_old = '<!-- stokowski:gate {"state": "g-old", "status": "waiting", "run": 1} -->'
    body_new = '<!-- stokowski:gate {"state": "g-new", "status": "waiting", "run": 1} -->'
    comments = [
        {"body": body_new, "createdAt": "2026-04-13T12:00:00.000Z"},
        {"body": body_old, "createdAt": "2026-04-10T08:00:00.000Z"},
    ]
    got = parse_latest_gate_waiting(comments)
    assert got is not None
    assert got["state"] == "g-new"


def test_parse_latest_gate_waiting_effective_time_max_payload_timestamp_and_created_at():
    """Same as state: max(JSON ts, createdAt) for waiting gates."""
    b_a = (
        '<!-- stokowski:gate {"state": "g-bound", "status": "waiting", "run": 1, '
        '"timestamp": "2026-01-01T00:00:00+00:00"} -->'
    )
    b_b = (
        '<!-- stokowski:gate {"state": "g-plain", "status": "waiting", "run": 1, '
        '"timestamp": "2026-06-01T00:00:00+00:00"} -->'
    )
    comments = [
        {"body": b_a, "createdAt": "2026-07-15T12:00:00.000Z"},
        {"body": b_b, "createdAt": "2026-06-01T12:00:00.000Z"},
    ]
    got = parse_latest_gate_waiting(comments)
    assert got is not None
    assert got["state"] == "g-bound"


def test_parse_latest_gate_waiting_tie_last_waiting_wins():
    ts = "2026-05-01T10:00:00+00:00"
    older = (
        f'<!-- stokowski:gate {{"state": "g-first", "status": "waiting", '
        f'"run": 1, "timestamp": "{ts}"}} -->'
    )
    newer = (
        f'<!-- stokowski:gate {{"state": "g-second", "status": "waiting", '
        f'"run": 1, "timestamp": "{ts}"}} -->'
    )
    comments = [{"body": older}, {"body": newer}]
    got = parse_latest_gate_waiting(comments)
    assert got is not None
    assert got["state"] == "g-second"


def test_get_last_gate_waiting_timestamp_returns_payload_timestamp_when_present():
    comments = [
        {
            "body": make_gate_comment("g1", "waiting", workflow="wf"),
            "createdAt": "2026-01-01T00:00:00.000Z",
        }
    ]
    ts = get_last_gate_waiting_timestamp(comments)
    assert ts is not None
    assert ts.endswith("+00:00")


def test_get_last_gate_waiting_timestamp_returns_none_when_no_waiting():
    comments = [{"body": make_gate_comment("g1", "approved", workflow="wf")}]
    assert get_last_gate_waiting_timestamp(comments) is None
