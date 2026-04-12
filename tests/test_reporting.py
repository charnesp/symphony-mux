"""Tests for report extraction module."""

from stokowski.models import Issue
from stokowski.reporting import (
    extract_report,
    format_no_report_comment,
    format_report_comment,
    has_approval_section,
)


def test_extract_report_finds_tag():
    """Extract report content from agent output with stokowski:report tag."""
    agent_output = """
    I've completed the work.

    <stokowski:report>
    ## Summary
    - Implemented feature X
    - Added tests
    </stokowski:report>

    Let me know if you need anything else.
    """

    result = extract_report(agent_output)

    assert result is not None
    assert "Implemented feature X" in result


def test_extract_report_prefers_last_pair_when_tag_mentioned_in_thinking():
    """NDJSON logs may mention <stokowski:report> in thinking before the real block."""
    # Mimics stream-json full_output: early line cites the tag, then tool noise, then real report
    agent_output = (
        '{"type":"assistant","message":{"content":[{"type":"thinking","thinking":"See '
        'prior `<stokowski:report>` for details."}]}}\n'
        '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash"}]}}\n'
        '{"type":"user","message":{"content":"stdout..."}}\n'
        '<stokowski:report>\n## Summary\n- Real report only\n</stokowski:report>\n'
    )

    result = extract_report(agent_output)

    assert result is not None
    assert "Real report only" in result
    assert "stdout" not in result
    assert "tool_use" not in result


def test_has_approval_section_detects_approval():
    """Detect when report contains approval section."""
    with_approval = "## Summary\n\n## Approval Required\nCheck this"
    without_approval = "## Summary\n\nJust summary"

    assert has_approval_section(with_approval) is True
    assert has_approval_section(without_approval) is False


def test_format_report_comment_includes_payload():
    """Format report as Linear comment with machine-readable payload."""
    issue = Issue(
        id="test-123",
        identifier="PROJ-1",
        title="Test issue",
        state="In Progress",
    )

    report = "## Summary\n- Done thing 1\n- Done thing 2"

    result = format_report_comment(
        report_content=report,
        issue=issue,
        state_name="implement",
        run=1,
        is_gate=True,
    )

    # Should contain machine-readable JSON payload
    assert "stokowski:report" in result
    assert '"type": "report"' in result
    assert "PROJ-1" in result
    assert "🚪 **Gate Review Required**" in result


def test_format_no_report_comment():
    """Format fallback comment when no report found."""
    issue = Issue(
        id="test-123",
        identifier="PROJ-1",
        title="Test issue",
        state="In Progress",
    )

    result = format_no_report_comment(
        issue=issue,
        state_name="implement",
        run=1,
    )

    assert "stokowski:report" in result
    assert '"has_approval_section": false' in result
    assert "without including a structured report" in result
