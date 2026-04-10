"""Tests for agent-gate routing marker extraction and resolution."""

from __future__ import annotations

import base64
import json

import pytest

from stokowski.agent_gate_route import (
    ROUTE_END,
    ROUTE_START,
    decide_agent_gate_transition,
    format_route_error_comment,
)
from stokowski.config import StateConfig

ROUTE_WRAP = """<<<STOKOWSKI_ROUTE>>>
{"transition": "%s"}
<<<END_STOKOWSKI_ROUTE>>>"""


def _gate_state_cfg() -> StateConfig:
    return StateConfig(
        name="route",
        type="agent-gate",
        prompt="p.md",
        default_transition="fallback",
        transitions={
            "pick_a": "state_a",
            "pick_b": "state_b",
            "fallback": "human_gate",
        },
    )


class TestDecideAgentGateTransition:
    def test_valid_block_known_key(self):
        cfg = _gate_state_cfg()
        out = "preamble\n" + ROUTE_WRAP % "pick_a" + "\ntrailer"
        key, err = decide_agent_gate_transition(out, cfg)
        assert key == "pick_a"
        assert err is None

    def test_missing_block_uses_default_transition(self):
        cfg = _gate_state_cfg()
        key, err = decide_agent_gate_transition("no markers here", cfg)
        assert key == "fallback"
        assert err is not None
        assert "missing" in err.lower() or "routing" in err.lower()

    def test_invalid_json_uses_default(self):
        cfg = _gate_state_cfg()
        bad = "<<<STOKOWSKI_ROUTE>>>\nnot json\n<<<END_STOKOWSKI_ROUTE>>>"
        key, err = decide_agent_gate_transition(bad, cfg)
        assert key == "fallback"
        assert err is not None
        assert "json" in err.lower()

    def test_unknown_transition_key_uses_default(self):
        cfg = _gate_state_cfg()
        out = ROUTE_WRAP % "nope"
        key, err = decide_agent_gate_transition(out, cfg)
        assert key == "fallback"
        assert err is not None
        assert "nope" in err or "unknown" in err.lower()

    def test_start_without_end_marker_uses_default_no_crash(self):
        cfg = _gate_state_cfg()
        bad = '<<<STOKOWSKI_ROUTE>>>\n{"transition": "pick_a"}\n'
        key, err = decide_agent_gate_transition(bad, cfg)
        assert key == "fallback"
        assert err is not None
        assert "end marker" in err.lower() or ROUTE_END.lower() in err.lower()

    def test_end_before_inner_content_still_no_valueerror(self):
        cfg = _gate_state_cfg()
        bad = f"{ROUTE_END}\n{ROUTE_START}\n{{}}\n"
        key, err = decide_agent_gate_transition(bad, cfg)
        assert key == "fallback"
        assert err is not None

    def test_missing_default_transition_falls_back_to_first_transition_key(self):
        cfg = StateConfig(
            name="route",
            type="agent-gate",
            prompt="p.md",
            default_transition=None,
            transitions={"first": "a", "second": "b"},
        )
        out = ROUTE_WRAP % "nope"
        key, err = decide_agent_gate_transition(out, cfg)
        assert key == "first"
        assert err is not None


class TestDecideFromClaudeNdjson:
    """Routing markers inside JSON string fields must use decoded text, not raw NDJSON."""

    def test_stream_json_result_field_parses_transition(self):
        cfg = _gate_state_cfg()
        visible = (
            "<stokowski:report>ok</stokowski:report>\n\n"
            "<<<STOKOWSKI_ROUTE>>>\n"
            '{"transition": "pick_a"}\n'
            "<<<END_STOKOWSKI_ROUTE>>>"
        )
        result_line = json.dumps({"type": "result", "result": visible})
        key, err = decide_agent_gate_transition(result_line, cfg)
        assert key == "pick_a"
        assert err is None

    def test_stream_json_assistant_text_parses_transition(self):
        cfg = _gate_state_cfg()
        visible = ROUTE_WRAP % "pick_b"
        assistant_line = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": visible}],
                },
            }
        )
        key, err = decide_agent_gate_transition(assistant_line, cfg)
        assert key == "pick_b"
        assert err is None

    def test_raw_ndjson_slice_between_markers_is_not_valid_json_without_decode(self):
        """Regression: substring on wire has escaped quotes; decoded text is required."""
        visible = ROUTE_WRAP % "pick_a"
        wire = json.dumps({"type": "result", "result": visible})
        # Between markers on the raw line, inner is \\n{\"transition\"... — not parseable JSON
        start = wire.index(ROUTE_START) + len(ROUTE_START)
        end = wire.index(ROUTE_END, start)
        inner = wire[start:end].strip()
        with pytest.raises(json.JSONDecodeError):
            json.loads(inner)

    def test_plain_text_routing_still_works(self):
        cfg = _gate_state_cfg()
        out = "preamble\n" + ROUTE_WRAP % "pick_a"
        key, err = decide_agent_gate_transition(out, cfg)
        assert key == "pick_a"
        assert err is None


class TestFormatRouteErrorComment:
    def test_machine_payload_is_base64_without_double_hyphen_risk(self):
        detail = 'bad-->break"}\n'
        body = format_route_error_comment(detail)
        assert body.startswith("<!-- stokowski:route-error b64:")
        inner = body.split("b64:", 1)[1].split(" -->", 1)[0]
        decoded = json.loads(base64.standard_b64decode(inner).decode("utf-8"))
        assert decoded["type"] == "route_error"
        assert "-->" in decoded["detail"]

    def test_human_section_contains_truncated_detail(self):
        long_detail = "x" * 600
        body = format_route_error_comment(long_detail)
        assert long_detail not in body
        assert "…" in body
