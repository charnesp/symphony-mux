"""Tests for 3-line dashboard agent message display.

Validates:
- RunAttempt.last_message stores up to 600 chars (not 200)
- Dashboard CSS allows 3-line wrapping with line-clamp
"""

import re

from stokowski.web import DASHBOARD_HTML


class TestRunnerLastMessageLimit:
    """Verify runner truncates last_message at 600 chars, not 200."""

    def test_claude_result_truncation_limit(self):
        """Claude runner _process_event should truncate result at 600 chars."""
        from stokowski.models import RunAttempt
        from stokowski.runner import _process_event

        attempt = RunAttempt(issue_id="test", issue_identifier="TEST-1")
        long_text = "x" * 800
        event = {"type": "result", "result": long_text, "usage": {}}
        _process_event(event, attempt, on_event=None, identifier="TEST-1")
        assert len(attempt.last_message) == 600, (
            f"Expected 600 chars, got {len(attempt.last_message)}"
        )

    def test_claude_assistant_string_content_truncation(self):
        """Claude runner should truncate assistant string content at 600 chars."""
        from stokowski.models import RunAttempt
        from stokowski.runner import _process_event

        attempt = RunAttempt(issue_id="test", issue_identifier="TEST-1")
        long_text = "y" * 800
        event = {"type": "assistant", "message": {"content": long_text}}
        _process_event(event, attempt, on_event=None, identifier="TEST-1")
        assert len(attempt.last_message) == 600, (
            f"Expected 600 chars, got {len(attempt.last_message)}"
        )

    def test_claude_assistant_list_content_truncation(self):
        """Claude runner should truncate assistant list content block at 600 chars."""
        from stokowski.models import RunAttempt
        from stokowski.runner import _process_event

        attempt = RunAttempt(issue_id="test", issue_identifier="TEST-1")
        long_text = "z" * 800
        event = {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": long_text}]},
        }
        _process_event(event, attempt, on_event=None, identifier="TEST-1")
        assert len(attempt.last_message) == 600, (
            f"Expected 600 chars, got {len(attempt.last_message)}"
        )


class TestDashboardAgentMsgCSS:
    """Verify .agent-msg CSS allows 3-line display."""

    def test_agent_msg_no_nowrap(self):
        """.agent-msg should NOT have white-space: nowrap (which forces 1 line)."""
        msg_match = re.search(r"\.agent-msg\s*\{([^}]+)\}", DASHBOARD_HTML, re.DOTALL)
        assert msg_match is not None, "No .agent-msg CSS rule found"
        css = msg_match.group(1)
        assert "nowrap" not in css, (
            ".agent-msg should not have white-space: nowrap — it forces single-line display"
        )

    def test_agent_msg_has_line_clamp(self):
        """.agent-msg should have -webkit-line-clamp: 3 for 3-line display."""
        msg_match = re.search(r"\.agent-msg\s*\{([^}]+)\}", DASHBOARD_HTML, re.DOTALL)
        assert msg_match is not None, "No .agent-msg CSS rule found"
        css = msg_match.group(1)
        assert "-webkit-line-clamp" in css, "Missing -webkit-line-clamp for line clamping"
        clamp_match = re.search(r"-webkit-line-clamp:\s*(\d+)", css)
        assert clamp_match is not None, "Could not parse -webkit-line-clamp value"
        assert clamp_match.group(1) == "3", (
            f"Expected -webkit-line-clamp: 3, got {clamp_match.group(1)}"
        )

    def test_agent_msg_has_overflow_hidden(self):
        """.agent-msg should have overflow: hidden for clamped text."""
        msg_match = re.search(r"\.agent-msg\s*\{([^}]+)\}", DASHBOARD_HTML, re.DOTALL)
        assert msg_match is not None
        css = msg_match.group(1)
        assert "overflow" in css and "hidden" in css, (
            ".agent-msg missing overflow: hidden needed for line clamping"
        )

    def test_agent_msg_has_box_orient(self):
        """.agent-msg should have -webkit-box-orient: vertical for line clamping."""
        msg_match = re.search(r"\.agent-msg\s*\{([^}]+)\}", DASHBOARD_HTML, re.DOTALL)
        assert msg_match is not None
        css = msg_match.group(1)
        assert "box-orient" in css, (
            ".agent-msg missing -webkit-box-orient: vertical for line clamping"
        )

    def test_agent_msg_has_webkit_box_display(self):
        """.agent-msg should have display: -webkit-box for line clamping."""
        msg_match = re.search(r"\.agent-msg\s*\{([^}]+)\}", DASHBOARD_HTML, re.DOTALL)
        assert msg_match is not None
        css = msg_match.group(1)
        assert "-webkit-box" in css, ".agent-msg missing display: -webkit-box for line clamping"

    def test_agent_msg_no_max_width(self):
        """.agent-msg should NOT have max-width (the grid column constrains width)."""
        msg_match = re.search(r"\.agent-msg\s*\{([^}]+)\}", DASHBOARD_HTML, re.DOTALL)
        assert msg_match is not None
        css = msg_match.group(1)
        assert "max-width" not in css, (
            ".agent-msg should not have max-width — the grid column constrains width"
        )
