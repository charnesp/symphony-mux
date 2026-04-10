"""State machine tracking via structured Linear comments."""

from __future__ import annotations

import contextlib
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("stokowski.tracking")

STATE_PATTERN = re.compile(r"<!-- stokowski:state ({.*?}) -->")
GATE_PATTERN = re.compile(r"<!-- stokowski:gate ({.*?}) -->")


def make_state_comment(state: str, run: int = 1, workflow: str | None = None) -> str:
    """Build a structured state-tracking comment."""
    payload: dict[str, Any] = {
        "state": state,
        "run": run,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if workflow:
        payload["workflow"] = workflow
    machine = f"<!-- stokowski:state {json.dumps(payload)} -->"
    wf_info = f" [{workflow}]" if workflow else ""
    human = f"**[Stokowski]** Entering state: **{state}**{wf_info} (run {run})"
    return f"{machine}\n\n{human}"


def make_gate_comment(
    state: str,
    status: str,
    prompt: str = "",
    rework_to: str | None = None,
    run: int = 1,
    workflow: str | None = None,
) -> str:
    """Build a structured gate-tracking comment."""
    payload: dict[str, Any] = {
        "state": state,
        "status": status,
        "run": run,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if rework_to:
        payload["rework_to"] = rework_to
    if workflow:
        payload["workflow"] = workflow

    machine = f"<!-- stokowski:gate {json.dumps(payload)} -->"

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

    return f"{machine}\n\n{human}"


def parse_latest_tracking(comments: list[dict]) -> dict[str, Any] | None:
    """Parse comments (oldest-first) to find the latest state or gate tracking entry.

    Returns a dict with keys:
        - "type": "state" or "gate"
        - Plus all fields from the JSON payload

    Returns None if no tracking comments found.
    """
    latest: dict[str, Any] | None = None

    for comment in comments:
        body = comment.get("body", "")

        state_match = STATE_PATTERN.search(body)
        if state_match:
            try:
                data = json.loads(state_match.group(1))
                data["type"] = "state"
                latest = data
            except json.JSONDecodeError:
                pass

        gate_match = GATE_PATTERN.search(body)
        if gate_match:
            try:
                data = json.loads(gate_match.group(1))
                data["type"] = "gate"
                latest = data
            except json.JSONDecodeError:
                pass

    return latest


def parse_latest_gate_waiting(comments: list[dict]) -> dict[str, Any] | None:
    """Return the most recent gate tracking payload with status "waiting".

    Comments are expected oldest-first (Linear order). Later comments win so
    the result is the chronologically last *waiting* gate, not the last gate
    comment of any status (e.g. approved after waiting).
    """
    latest_waiting: dict[str, Any] | None = None

    for comment in comments:
        body = comment.get("body", "")
        gate_match = GATE_PATTERN.search(body)
        if not gate_match:
            continue
        try:
            data = json.loads(gate_match.group(1))
        except json.JSONDecodeError:
            continue
        if data.get("status") != "waiting":
            continue
        latest_waiting = dict(data)
        latest_waiting["type"] = "gate"

    return latest_waiting


def get_last_tracking_timestamp(comments: list[dict]) -> str | None:
    """Find the timestamp of the latest tracking comment."""
    latest_ts: str | None = None

    for comment in comments:
        body = comment.get("body", "")
        for pattern in (STATE_PATTERN, GATE_PATTERN):
            match = pattern.search(body)
            if match:
                try:
                    data = json.loads(match.group(1))
                    ts = data.get("timestamp")
                    if ts:
                        latest_ts = ts
                except json.JSONDecodeError:
                    pass

    return latest_ts


def get_comments_since(comments: list[dict], since_timestamp: str | None) -> list[dict]:
    """Filter comments to only those after a given timestamp.

    Returns comments that are NOT stokowski tracking comments and
    were created after the given timestamp.
    """
    result = []
    since_dt = None
    if since_timestamp:
        with contextlib.suppress(ValueError, AttributeError):
            since_dt = datetime.fromisoformat(since_timestamp.replace("Z", "+00:00"))

    for comment in comments:
        body = comment.get("body", "")
        if "<!-- stokowski:" in body:
            continue

        if since_dt:
            created = comment.get("createdAt", "")
            if created:
                try:
                    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if created_dt <= since_dt:
                        continue
                except (ValueError, AttributeError):
                    pass

        result.append(comment)

    return result
