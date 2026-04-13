"""Balanced JSON extraction for <!-- stokowski:state|gate {...} --> markers."""

from __future__ import annotations

import json

from stokowski.tracking import get_comments_since, parse_latest_tracking


def test_parse_latest_tracking_json_with_false_close_sequence_inside_string():
    """Regex would stop at first `} -->` inside a string; balanced parser must not."""
    payload = {
        "note": "} --> trick",
        "state": "y",
        "run": 1,
        "timestamp": "2026-01-01T00:00:00+00:00",
    }
    machine = f"<!-- stokowski:state {json.dumps(payload)} -->\n\nx"
    got = parse_latest_tracking([{"body": machine, "createdAt": "2026-01-01T00:00:00Z"}])
    assert got is not None
    assert got["state"] == "y"
    assert got["note"] == "} --> trick"


def test_parse_latest_tracking_json_with_brace_inside_string_value():
    payload = {
        "state": "x",
        "run": 1,
        "hint": "literal } in text",
        "timestamp": "2026-01-15T12:00:00+00:00",
    }
    machine = f"<!-- stokowski:state {json.dumps(payload)} -->\n\nhuman"
    got = parse_latest_tracking([{"body": machine, "createdAt": "2026-01-15T12:00:01Z"}])
    assert got is not None
    assert got["type"] == "state"
    assert got["state"] == "x"
    assert got["hint"] == "literal } in text"


def test_get_comments_since_invalid_since_returns_empty_when_since_provided():
    """Non-parseable since_timestamp: do not include all human comments."""
    comments = [
        {"body": "Hello", "createdAt": "2026-06-01T00:00:00Z"},
    ]
    assert get_comments_since(comments, "not-a-valid-iso") == []


def test_get_comments_since_excludes_human_without_created_at_when_since_bound():
    """With a strict since boundary, omit human comments with missing/unparseable createdAt."""
    comments = [
        {"body": "Undated review feedback", "id": "a"},
        {"body": "Dated reply", "createdAt": "2026-06-02T00:00:00Z", "id": "b"},
    ]
    got = get_comments_since(comments, "2026-06-01T00:00:00Z")
    assert len(got) == 1
    assert got[0]["id"] == "b"


def test_get_comments_since_includes_undated_human_when_no_since_bound():
    comments = [{"body": "Undated", "id": "a"}]
    assert get_comments_since(comments, None) == comments


def test_get_comments_since_excludes_tracking_case_insensitive_prefix():
    comments = [
        {"body": "<!-- Stokowski:state {\"state\": \"s\"} -->", "createdAt": "2026-01-01T00:00:00Z"},
        {"body": "Human note", "createdAt": "2026-01-02T00:00:00Z"},
    ]
    out = get_comments_since(comments, None)
    assert len(out) == 1
    assert out[0]["body"] == "Human note"


def test_parse_latest_tracking_state_gate_tie_same_effective_time_last_in_body_wins():
    ts = "2026-03-01T10:00:00+00:00"
    body = (
        f'<!-- stokowski:state {{"state": "s", "run": 1, "timestamp": "{ts}"}} -->'
        f'<!-- stokowski:gate {{"state": "g", "status": "waiting", "run": 1, "timestamp": "{ts}"}} -->'
    )
    got = parse_latest_tracking(
        [{"body": body, "createdAt": "2026-03-01T10:00:00.000Z"}]
    )
    assert got is not None
    assert got["type"] == "gate"
    assert got["state"] == "g"

