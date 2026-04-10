"""Tests for recovering the last gate comment with status waiting."""

from __future__ import annotations

from stokowski.tracking import (
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
    assert parse_latest_tracking([c1, c2])["type"] == "state"
    got = parse_latest_gate_waiting([c1, c2])
    assert got is not None
    assert got["state"] == "human"
    assert got["status"] == "waiting"


def test_parse_latest_gate_waiting_none_when_no_waiting():
    c1 = {"body": make_gate_comment("human", "approved", workflow="wf")}
    assert parse_latest_gate_waiting([c1]) is None
