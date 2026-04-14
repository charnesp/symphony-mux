"""State machine tracking via structured Linear comments."""

from __future__ import annotations

import base64
import binascii
import json
import logging
from datetime import UTC, datetime
from typing import Any

from .datetime_parse import parse_linear_iso_datetime

logger = logging.getLogger("stokowski.tracking")

# Marker prefix for BASE64-encoded tracking data
STOKOWSKI64_PREFIX = "stokowski64:"


def _encode_marker(payload: dict[str, Any]) -> str:
    """Encode a payload as BASE64 stokowski64 marker."""
    json_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    b64 = base64.standard_b64encode(json_bytes).decode("ascii")
    return f"{STOKOWSKI64_PREFIX}{b64}"


def make_state_comment(state: str, run: int = 1, workflow: str | None = None) -> str:
    """Build a structured state-tracking comment with BASE64 marker at end."""
    payload: dict[str, Any] = {
        "type": "state",
        "state": state,
        "run": run,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if workflow:
        payload["workflow"] = workflow
    machine = _encode_marker(payload)
    wf_info = f" [{workflow}]" if workflow else ""
    human = f"**[Stokowski]** Entering state: **{state}**{wf_info} (run {run})"
    return f"{human}\n\n{machine}"


def make_gate_comment(
    state: str,
    status: str,
    prompt: str = "",
    rework_to: str | None = None,
    run: int = 1,
    workflow: str | None = None,
) -> str:
    """Build a structured gate-tracking comment with BASE64 marker at end."""
    payload: dict[str, Any] = {
        "type": "gate",
        "state": state,
        "status": status,
        "run": run,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if rework_to:
        payload["rework_to"] = rework_to
    if workflow:
        payload["workflow"] = workflow

    machine = _encode_marker(payload)

    if status == "waiting":
        human = f"**[Stokowski]** Awaiting human review: **{state}**"
        if prompt:
            human += f" — {prompt}"
    elif status == "approved":
        human = f"**[Stokowski]** Gate **{state}** approved."
    elif status == "rework":
        human = f"**[Stokowski]** Rework requested at **{state}**. Returning to: **{rework_to}**"
        if run > 1:
            human += f" (run {run})"
    elif status == "escalated":
        human = (
            f"**[Stokowski]** Max rework exceeded at **{state}**. "
            f"Escalating for human intervention."
        )
    else:
        human = f"**[Stokowski]** Gate **{state}** status: {status}"

    return f"{human}\n\n{machine}"


def parse_latest_tracking(comments: list[dict]) -> dict[str, Any] | None:
    """Return the most recent state or gate tracking entry.

    Picks the candidate with the latest **effective time** per marker: when both
    parse, ``max(JSON timestamp, Linear createdAt)`` (so the instant is not
    earlier than the comment existed); otherwise whichever field parses. Order
    of comments in the API response does not matter. Values are normalized to
    UTC; naive strings are treated as UTC. Ties use the **last** marker in scan
    order among those tied for max time. Multiple ``stokowski:`` markers in one
    comment are ordered by position in the body.

    If no candidate has a parseable time, falls back to the last marker in
    scan order (document order within each comment, then comment list order).

    Returns a dict with ``type`` ``"state"`` or ``"gate"`` plus JSON fields,
    or None if no tracking markers found.
    """
    entries = _collect_tracking_entries(comments)
    if not entries:
        return None
    row, _src = _resolve_best_tracking_row(entries)
    return row


def _parse_iso_datetime(value: str | None) -> datetime | None:
    """Parse an ISO-8601 string to an aware UTC datetime (shared with ``linear``)."""
    return parse_linear_iso_datetime(value)


def _payload_timestamp_string(payload: dict[str, Any]) -> str | None:
    v = payload.get("timestamp")
    if isinstance(v, str) and v.strip():
        return v
    return None


def _extract_balanced_json_object(body: str, open_brace: int) -> tuple[int, str] | None:
    """``open_brace`` indexes ``{``. Returns ``(index_after_closing_brace, json_slice)``."""
    if open_brace >= len(body) or body[open_brace] != "{":
        return None
    depth = 0
    i = open_brace
    in_str = False
    esc = False
    while i < len(body):
        c = body[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1, body[open_brace : i + 1]
        i += 1
    return None


def _skip_stokowski_html_close(body: str, after_json: int) -> int | None:
    """Return index after ``-->`` following JSON, or None."""
    k = after_json
    while k < len(body) and body[k] in " \t\n\r":
        k += 1
    if body[k : k + 3] != "-->":
        return None
    return k + 3


def _iter_stokowski_marker_json(body: str, marker: str) -> list[tuple[int, str]]:
    """``marker`` is ``state`` or ``gate``. Each hit: ``(start_offset, json_str)``.

    Supports both legacy HTML comment format (<!-- stokowski:TYPE {...} -->)
    and new BASE64 format (stokowski64:...).
    """
    # First try the new BASE64 format - filter by type embedded in JSON
    out: list[tuple[int, str]] = []
    for pos, json_str in _iter_stokowski64_markers(body, marker_type=marker):
        out.append((pos, json_str))

    # Then try legacy HTML comment format
    prefix = f"<!-- stokowski:{marker} "
    pos = 0
    plen = len(prefix)
    while pos <= len(body) - plen:
        i = body.find(prefix, pos)
        if i == -1:
            break
        j = i + plen
        while j < len(body) and body[j] in " \t\n\r":
            j += 1
        if j >= len(body) or body[j] != "{":
            pos = i + 1
            continue
        bal = _extract_balanced_json_object(body, j)
        if bal is None:
            logger.warning("Unbalanced JSON in stokowski:%s marker at offset %s", marker, i)
            pos = i + 1
            continue
        end_json, json_str = bal
        end_comment = _skip_stokowski_html_close(body, end_json)
        if end_comment is None:
            pos = i + 1
            continue
        out.append((i, json_str))
        pos = end_comment
    return out


def _iter_stokowski64_markers(body: str, marker_type: str | None = None) -> list[tuple[int, str]]:
    """Find all stokowski64: markers in body. Returns list of (start_offset, json_str).

    Args:
        body: The comment body to search.
        marker_type: Optional type to filter by ("state", "gate", "report", "route_error").
                    If None, returns all markers.
    """
    out: list[tuple[int, str]] = []
    pos = 0
    prefix_len = len(STOKOWSKI64_PREFIX)

    while pos <= len(body) - prefix_len:
        i = body.find(STOKOWSKI64_PREFIX, pos)
        if i == -1:
            break

        # Extract the BASE64 data after the prefix
        b64_start = i + prefix_len
        # Find end of BASE64 data (whitespace or end of string)
        b64_end = b64_start
        while b64_end < len(body) and body[b64_end] not in " \t\n\r":
            b64_end += 1

        b64_data = body[b64_start:b64_end]
        if b64_data:
            try:
                json_bytes = base64.standard_b64decode(b64_data)
                json_str = json_bytes.decode("utf-8")
                # Validate it's valid JSON and check type if specified
                payload = json.loads(json_str)
                if marker_type is None or payload.get("type") == marker_type:
                    out.append((i, json_str))
            except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as e:
                logger.debug("Invalid stokowski64 marker at offset %s: %s", i, e)

        pos = b64_end if b64_end > b64_start else i + prefix_len

    return out


def _tracking_payload_effective_time(
    comment: dict[str, Any], payload: dict[str, Any]
) -> datetime | None:
    """UTC instant for ordering: max(parsed JSON timestamp, comment createdAt) when both exist.

    Ensures the effective time is not earlier than the Linear comment creation
    time. If only one field parses, that value is used.
    """
    ts = _parse_iso_datetime(_payload_timestamp_string(payload))
    ca = _parse_iso_datetime(comment.get("createdAt"))
    if ts is not None and ca is not None:
        return max(ts, ca)
    return ts or ca


def _resolve_best_tracking_row(
    entries: list[tuple[datetime | None, dict[str, Any], dict[str, Any]]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(row, source_comment)`` for the latest effective time, or last entry if none parse.

    When multiple entries have the same effective time, the last one in the list wins.
    """
    best: tuple[datetime, dict[str, Any], dict[str, Any], int] | None = None
    for idx, (eff, row, comment) in enumerate(entries):
        if eff is None:
            continue
        # Tie-breaking: last entry wins. We use > (not >=) to ensure last wins
        # but include index in comparison to avoid dict comparison.
        if best is None or eff > best[0] or (eff == best[0] and idx > best[3]):
            best = (eff, row, comment, idx)
    if best is not None:
        return best[1], best[2]
    return entries[-1][1], entries[-1][2]


def _collect_tracking_entries(
    comments: list[dict],
) -> list[tuple[datetime | None, dict[str, Any], dict[str, Any]]]:
    """Each ``stokowski:state`` / ``stokowski:gate`` marker → (effective_time, row, comment).

    Markers in the same comment are ordered by start offset in the body (all
    state and gate matches merged and sorted).
    """
    entries: list[tuple[datetime | None, dict[str, Any], dict[str, Any]]] = []

    for comment in comments:
        body = comment.get("body", "")
        markers: list[tuple[int, str, str]] = []
        for pos, json_raw in _iter_stokowski_marker_json(body, "state"):
            markers.append((pos, "state", json_raw))
        for pos, json_raw in _iter_stokowski_marker_json(body, "gate"):
            markers.append((pos, "gate", json_raw))
        markers.sort(key=lambda t: t[0])

        for _pos, kind, json_raw in markers:
            try:
                raw = json.loads(json_raw)
            except json.JSONDecodeError as e:
                logger.warning("Invalid JSON in stokowski:%s marker: %s", kind, e)
                continue
            row = dict(raw)
            row["type"] = kind
            eff = _tracking_payload_effective_time(comment, raw)
            entries.append((eff, row, comment))

    return entries


def parse_latest_gate_waiting(comments: list[dict]) -> dict[str, Any] | None:
    """Return the most recent gate tracking payload with status "waiting".

    Uses the same effective-time rules as :func:`parse_latest_tracking` on the
    subset of gate markers with ``status == "waiting"``. Ties: last wins.

    If no candidate has a parseable time, falls back to the last waiting gate
    in document/list scan order.
    """
    entries = _collect_tracking_entries(comments)
    waiting = [
        (eff, row, c)
        for eff, row, c in entries
        if row.get("type") == "gate" and row.get("status") == "waiting"
    ]
    if not waiting:
        return None
    row, _src = _resolve_best_tracking_row(waiting)
    return row


def get_last_gate_waiting_timestamp(comments: list[dict]) -> str | None:
    """ISO timestamp string for the most recent waiting gate marker.

    Uses the same effective-time rules and tie-breaking as
    :func:`parse_latest_gate_waiting`. Prefers payload ``timestamp``; falls back
    to the source comment ``createdAt``.
    """
    entries = _collect_tracking_entries(comments)
    waiting = [
        (eff, row, c)
        for eff, row, c in entries
        if row.get("type") == "gate" and row.get("status") == "waiting"
    ]
    if not waiting:
        return None

    row, comment = _resolve_best_tracking_row(waiting)
    ts = _payload_timestamp_string(row)
    if ts:
        return ts
    created = comment.get("createdAt")
    if isinstance(created, str) and created.strip():
        return created
    return None


def get_last_tracking_timestamp(comments: list[dict]) -> str | None:
    """ISO timestamp string for the same tracking entry as :func:`parse_latest_tracking`.

    Prefers the payload's ``timestamp`` field; if missing, returns the
    comment's ``createdAt`` string for that entry.
    """
    entries = _collect_tracking_entries(comments)
    if not entries:
        return None

    row, comment = _resolve_best_tracking_row(entries)

    ts = _payload_timestamp_string(row)
    if ts:
        return ts
    created = comment.get("createdAt")
    if isinstance(created, str) and created.strip():
        return created
    return None


def _comment_body_is_stokowski_tracking(body: str) -> bool:
    """Check if body contains any stokowski tracking markers (legacy or BASE64)."""
    body_lower = body.casefold()
    return "<!-- stokowski:" in body_lower or "stokowski64:" in body_lower


def get_comments_since(comments: list[dict], since_timestamp: str | None) -> list[dict]:
    """Filter comments to only those after a given timestamp.

    Returns comments that are NOT stokowski tracking comments and
    were created after the given timestamp. If ``since_timestamp`` is
    non-empty but not parseable, returns an empty list (strict boundary).
    When a since bound is set, human comments without a parseable
    ``createdAt`` are excluded (unknown time vs boundary).
    """
    result = []
    if since_timestamp:
        since_dt = _parse_iso_datetime(since_timestamp)
        if since_dt is None:
            return []
    else:
        since_dt = None

    for comment in comments:
        body = comment.get("body", "")
        if _comment_body_is_stokowski_tracking(body):
            continue

        if since_dt:
            created = comment.get("createdAt", "")
            created_dt = _parse_iso_datetime(created) if created else None
            if created_dt is None:
                continue
            if created_dt <= since_dt:
                continue

        result.append(comment)

    return result
