"""Parse agent-gate routing markers from runner output."""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING

__all__ = ["ROUTE_END", "ROUTE_START", "decide_agent_gate_transition", "format_route_error_comment"]

if TYPE_CHECKING:
    from .config import StateConfig

ROUTE_START = "<<<STOKOWSKI_ROUTE>>>"
ROUTE_END = "<<<END_STOKOWSKI_ROUTE>>>"

_MAX_ROUTE_ERR_DETAIL = 500
_MAX_TRANSITION_PREVIEW = 120


def _visible_text_from_claude_ndjson(full_output: str) -> str:
    """Rebuild visible assistant/result text from Claude ``stream-json`` NDJSON lines.

    On the wire, each line is a JSON object; user-visible prose (including routing markers)
    lives inside JSON string fields with ``\\n`` and ``\\\"`` escapes. Substring search on the
    raw line sees those escapes, so ``json.loads`` on the slice between markers fails. This
    function decodes ``assistant`` / ``result`` events and concatenates their text fields so
    routing JSON is real JSON again.
    """
    chunks: list[str] = []
    for raw_line in full_output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        et = event.get("type")
        if et == "result":
            r = event.get("result")
            if isinstance(r, str) and r.strip():
                chunks.append(r)
        elif et == "assistant":
            msg = event.get("message") or {}
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                chunks.append(content)
            elif isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "text":
                        continue
                    t = block.get("text")
                    if isinstance(t, str) and t.strip():
                        chunks.append(t)
    return "\n".join(chunks)


def _try_parse_routing_block(blob: str, state_cfg: StateConfig) -> tuple[str | None, str | None]:
    """Parse routing from ``blob``. Returns ``(transition_key, None)`` on success, else
    ``(None, error_detail)``. If ``ROUTE_START`` is absent, returns ``(None, None)``.
    """
    if ROUTE_START not in blob:
        return None, None

    start_idx = blob.index(ROUTE_START) + len(ROUTE_START)
    try:
        end_idx = blob.index(ROUTE_END, start_idx)
    except ValueError:
        return None, f"Routing block missing end marker ({ROUTE_END}) after {ROUTE_START}"

    inner = blob[start_idx:end_idx].strip()

    try:
        data = json.loads(inner)
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON in routing block: {e}"

    if not isinstance(data, dict):
        return None, "Routing JSON must be a JSON object with a 'transition' field"

    tr = data.get("transition")
    if not isinstance(tr, str) or not tr.strip():
        return None, "Routing JSON 'transition' must be a non-empty string"

    tr = tr.strip()
    if tr not in state_cfg.transitions:
        preview = tr[:_MAX_TRANSITION_PREVIEW] + ("…" if len(tr) > _MAX_TRANSITION_PREVIEW else "")
        return None, f"Unknown transition key {preview!r} in routing output"

    return tr, None


def decide_agent_gate_transition(
    full_output: str, state_cfg: StateConfig
) -> tuple[str, str | None]:
    """Choose the transition key from runner output and optional human-facing error text.

    On any parse failure or unknown transition name, returns ``(default_transition, error_message)``.
    On success returns ``(chosen_key, None)``.

    Tries decoded Claude NDJSON text first (see :func:`_visible_text_from_claude_ndjson`), then
    the raw ``full_output`` (plain prompts / tests / other runners).
    """
    default_key = (state_cfg.default_transition or "").strip() or None
    if not default_key:
        keys = list(state_cfg.transitions.keys())
        if keys:
            default_key = keys[0]
        else:
            return "complete", (
                "agent-gate state has no default_transition and no transitions (config error)"
            )

    decoded = _visible_text_from_claude_ndjson(full_output)
    blobs: list[str] = []
    if decoded.strip():
        blobs.append(decoded)
    blobs.append(full_output)

    any_start = False
    last_err: str | None = None
    for blob in blobs:
        if ROUTE_START not in blob:
            continue
        any_start = True
        key, err = _try_parse_routing_block(blob, state_cfg)
        if err is None and key is not None:
            return key, None
        if err is not None:
            last_err = err

    if not any_start:
        return (
            default_key,
            f"Routing block missing (expected {ROUTE_START} ... {ROUTE_END})",
        )

    return default_key, last_err or "Routing block could not be parsed"


def format_route_error_comment(detail: str) -> str:
    """Build a Linear comment when automatic agent-gate routing failed."""
    safe = detail.strip()
    if len(safe) > _MAX_ROUTE_ERR_DETAIL:
        safe = safe[:_MAX_ROUTE_ERR_DETAIL] + "…"
    payload = json.dumps({"type": "route_error", "detail": safe}, separators=(",", ":"))
    b64 = base64.standard_b64encode(payload.encode("utf-8")).decode("ascii")
    return (
        f"<!-- stokowski:route-error b64:{b64} -->\n\n"
        f"**[Stokowski] Agent-gate routing fallback.**\n\n{safe}"
    )
