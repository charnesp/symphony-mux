"""parse_latest_tracking and get_last_tracking_timestamp use max(effective time), not list order."""

from __future__ import annotations

from stokowski.tracking import get_last_tracking_timestamp, parse_latest_tracking


def test_parse_latest_tracking_picks_newest_state_by_json_timestamp_not_list_order():
    older = (
        '<!-- stokowski:state {"state": "investigate", "run": 1, '
        '"timestamp": "2026-04-01T10:00:00+00:00", "workflow": "feature"} -->'
    )
    newer = (
        '<!-- stokowski:state {"state": "implement", "run": 1, '
        '"timestamp": "2026-04-13T08:00:00+00:00", "workflow": "feature"} -->'
    )
    comments = [
        {"body": newer, "createdAt": "2026-04-13T08:00:01.000Z"},
        {"body": older, "createdAt": "2026-04-01T10:00:01.000Z"},
    ]
    got = parse_latest_tracking(comments)
    assert got is not None
    assert got["type"] == "state"
    assert got["state"] == "implement"


def test_parse_latest_tracking_state_vs_gate_wins_by_newer_timestamp():
    gate_body = (
        '<!-- stokowski:gate {"state": "merge-review", "status": "waiting", "run": 2, '
        '"timestamp": "2026-04-12T21:20:50+00:00", "workflow": "feature"} -->'
    )
    state_body = (
        '<!-- stokowski:state {"state": "investigate", "run": 2, '
        '"timestamp": "2026-04-13T10:00:00+00:00", "workflow": "feature"} -->'
    )
    # Newest-first: state comment listed before older gate
    comments = [
        {"body": state_body, "createdAt": "2026-04-13T10:00:01.000Z"},
        {"body": gate_body, "createdAt": "2026-04-12T21:20:51.000Z"},
    ]
    got = parse_latest_tracking(comments)
    assert got is not None
    assert got["type"] == "state"
    assert got["state"] == "investigate"


def test_parse_latest_tracking_fallback_last_candidate_when_no_parseable_time():
    """No JSON timestamp and no createdAt: preserve legacy last-in-order among markers."""
    b1 = '<!-- stokowski:state {"state": "a", "run": 1} -->'
    b2 = '<!-- stokowski:state {"state": "b", "run": 1} -->'
    comments = [{"body": b1}, {"body": b2}]
    got = parse_latest_tracking(comments)
    assert got is not None
    assert got["state"] == "b"


def test_get_last_tracking_timestamp_matches_parse_latest_effective_time():
    gate_body = (
        '<!-- stokowski:gate {"state": "g", "status": "waiting", "run": 1, '
        '"timestamp": "2026-01-02T00:00:00+00:00"} -->'
    )
    state_body = (
        '<!-- stokowski:state {"state": "s", "run": 1, '
        '"timestamp": "2026-01-03T00:00:00+00:00"} -->'
    )
    comments = [
        {"body": gate_body, "createdAt": "2026-01-02T12:00:00Z"},
        {"body": state_body, "createdAt": "2026-01-03T12:00:00Z"},
    ]
    got_ts = parse_latest_tracking(comments)
    assert got_ts is not None
    assert got_ts["state"] == "s"
    assert get_last_tracking_timestamp(comments) == "2026-01-03T00:00:00+00:00"


def test_parse_latest_tracking_tie_last_marker_wins():
    ts = "2026-04-01T12:00:00+00:00"
    b1 = f'<!-- stokowski:state {{"state": "first", "run": 1, "timestamp": "{ts}"}} -->'
    b2 = f'<!-- stokowski:state {{"state": "second", "run": 1, "timestamp": "{ts}"}} -->'
    comments = [{"body": b1}, {"body": b2}]
    got_tie = parse_latest_tracking(comments)
    assert got_tie is not None
    assert got_tie["state"] == "second"


def test_parse_latest_tracking_naive_timestamp_assumed_utc_comparable():
    """Naive JSON timestamps are interpreted as UTC; no TypeError vs aware values."""
    b1 = '<!-- stokowski:state {"state": "a", "run": 1, "timestamp": "2026-04-01T12:00:00"} -->'
    b2 = '<!-- stokowski:state {"state": "b", "run": 1, "timestamp": "2026-04-01T12:00:00+00:00"} -->'
    comments = [{"body": b1}, {"body": b2}]
    got = parse_latest_tracking(comments)
    assert got is not None
    assert got["state"] == "b"


def test_parse_latest_tracking_same_instant_different_offset_last_wins():
    b1 = '<!-- stokowski:state {"state": "a", "run": 1, "timestamp": "2026-04-01T12:00:00+00:00"} -->'
    b2 = '<!-- stokowski:state {"state": "b", "run": 1, "timestamp": "2026-04-01T14:00:00+02:00"} -->'
    comments = [{"body": b1}, {"body": b2}]
    got_offset = parse_latest_tracking(comments)
    assert got_offset is not None
    assert got_offset["state"] == "b"


def test_effective_time_is_max_of_payload_timestamp_and_created_at():
    """Payload cannot order before comment creation: max(JSON ts, createdAt)."""
    b_a = '<!-- stokowski:state {"state": "bound-wins", "run": 1, "timestamp": "2026-01-01T00:00:00+00:00"} -->'
    b_b = '<!-- stokowski:state {"state": "plain-newer-ts", "run": 1, "timestamp": "2026-06-01T00:00:00+00:00"} -->'
    comments = [
        {"body": b_a, "createdAt": "2026-07-15T12:00:00.000Z"},
        {"body": b_b, "createdAt": "2026-06-01T12:00:00.000Z"},
    ]
    got = parse_latest_tracking(comments)
    assert got is not None
    assert got["state"] == "bound-wins"


def test_invalid_payload_timestamp_falls_back_to_created_at():
    b_bad = (
        '<!-- stokowski:state {"state": "bad-ts", "run": 1, "timestamp": "not-a-date", '
        '"workflow": "feature"} -->'
    )
    b_ok = '<!-- stokowski:state {"state": "ok-ts", "run": 1, "timestamp": "2026-02-01T00:00:00+00:00"} -->'
    comments = [
        {"body": b_bad, "createdAt": "2026-05-01T00:00:00.000Z"},
        {"body": b_ok, "createdAt": "2026-02-01T00:00:00.000Z"},
    ]
    got_bad = parse_latest_tracking(comments)
    assert got_bad is not None
    assert got_bad["state"] == "bad-ts"


def test_two_state_markers_in_one_comment_ordered_by_body_position():
    body = (
        '<!-- stokowski:state {"state": "first-in-body", "run": 1, "timestamp": "2026-01-01T00:00:00+00:00"} -->'
        "\n"
        '<!-- stokowski:state {"state": "second-in-body", "run": 1, "timestamp": "2026-02-01T00:00:00+00:00"} -->'
    )
    comments = [{"body": body, "createdAt": "2026-01-01T00:00:00.000Z"}]
    got_two = parse_latest_tracking(comments)
    assert got_two is not None
    assert got_two["state"] == "second-in-body"


def test_parse_latest_tracking_created_at_only_newest_first_list():
    b_old = '<!-- stokowski:state {"state": "old", "run": 1} -->'
    b_new = '<!-- stokowski:state {"state": "new", "run": 1} -->'
    comments = [
        {"body": b_new, "createdAt": "2026-04-13T12:00:00.000Z"},
        {"body": b_old, "createdAt": "2026-04-01T08:00:00.000Z"},
    ]
    got_new = parse_latest_tracking(comments)
    assert got_new is not None
    assert got_new["state"] == "new"


def test_get_last_tracking_timestamp_returns_created_at_when_no_payload_timestamp():
    body = '<!-- stokowski:state {"state": "x", "run": 1} -->'
    comments = [{"body": body, "createdAt": "2026-08-20T10:00:00.000Z"}]
    got_x = parse_latest_tracking(comments)
    assert got_x is not None
    assert got_x["state"] == "x"
    assert get_last_tracking_timestamp(comments) == "2026-08-20T10:00:00.000Z"
