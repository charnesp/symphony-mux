"""Report extraction and posting for agent work summaries."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Issue

# Opening / closing tags (case-insensitive matching via separate patterns)
REPORT_OPEN_PATTERN = re.compile(r"<stokowski:report>", re.IGNORECASE)
REPORT_CLOSE_PATTERN = re.compile(r"</stokowski:report>", re.IGNORECASE)

APPROVAL_SECTION_PATTERN = re.compile(
    r"(?:##|###)\s*(?:Approval Required|Éléments? à valider|Items? (?:Needing|Requiring) Approval)",
    re.IGNORECASE,
)


def extract_report(agent_output: str) -> str | None:
    """Extract the stokowski report from agent output.

    Stream-json ``full_output`` is often the entire NDJSON log joined with newlines.
    Models may mention ``<stokowski:report>`` earlier (e.g. in a *thinking* block) without
    intending a real tag. Taking the *first* open + *first* close would then span the
    whole stream. We use the **last** closing tag and the **last** opening tag before it.

    Args:
        agent_output: The full text output from the agent.

    Returns:
        The content inside <stokowski:report> tags, or None if not found.
    """
    if not agent_output:
        return None
    close_matches = list(REPORT_CLOSE_PATTERN.finditer(agent_output))
    if not close_matches:
        return None
    for close_m in reversed(close_matches):
        prefix = agent_output[: close_m.start()]
        open_matches = list(REPORT_OPEN_PATTERN.finditer(prefix))
        if not open_matches:
            continue
        last_open = open_matches[-1]
        content = agent_output[last_open.end() : close_m.start()].strip()
        content = content.replace("\\n", "\n")
        return content
    return None


def has_approval_section(report_content: str) -> bool:
    """Check if the report contains an approval/gate section.

    Args:
        report_content: The extracted report content.

    Returns:
        True if an approval section is detected.
    """
    return bool(APPROVAL_SECTION_PATTERN.search(report_content))


def format_report_comment(
    report_content: str,
    issue: Issue,
    state_name: str,
    run: int,
    is_gate: bool = False,
) -> str:
    """Format the report as a Linear comment.

    Creates a structured comment with machine-readable JSON in HTML comment
    and human-readable markdown.

    Args:
        report_content: The extracted report content.
        issue: The Linear issue being worked on.
        state_name: Current state machine state.
        run: Current run number.
        is_gate: Whether this report is for a gate transition.

    Returns:
        Formatted comment ready to post to Linear.
    """
    payload = {
        "type": "report",
        "state": state_name,
        "run": run,
        "timestamp": datetime.now(UTC).isoformat(),
        "has_approval_section": has_approval_section(report_content),
        "is_gate": is_gate,
    }

    lines = [
        f"<!-- stokowski:report {json.dumps(payload)} -->",
        "",
        f"## 📝 Work Report — Run {run}",
        "",
        f"**Issue:** {issue.identifier} — {issue.title}",
        f"**State:** `{state_name}`",
        "",
        "---",
        "",
        report_content,
    ]

    if is_gate:
        lines.extend(
            [
                "",
                "---",
                "",
                "🚪 **Gate Review Required**",
                "",
                "This work is awaiting human review. Please:",
                "- Review the items listed above",
                "- Use Linear state transitions to approve or request rework",
                "",
            ]
        )

    return "\n".join(lines)


def format_no_report_comment(
    issue: Issue,
    state_name: str,
    run: int,
) -> str:
    """Format a fallback comment when no report was found.

    This is used when the agent completes but didn't include a report tag.

    Args:
        issue: The Linear issue being worked on.
        state_name: Current state machine state.
        run: Current run number.

    Returns:
        Formatted fallback comment.
    """
    payload = {
        "type": "report",
        "state": state_name,
        "run": run,
        "timestamp": datetime.now(UTC).isoformat(),
        "has_approval_section": False,
        "is_gate": False,
        "note": "No stokowski:report tag found in agent output",
    }

    return (
        f"<!-- stokowski:report {json.dumps(payload)} -->\n"
        f"\n"
        f"## 📝 Work Report — Run {run}\n"
        f"\n"
        f"**Issue:** {issue.identifier} — {issue.title}\n"
        f"**State:** `{state_name}`\n"
        f"\n"
        f"---\n"
        f"\n"
        f"*The agent completed without including a structured report. "
        f"Review the agent's output directly for details.*"
    )
