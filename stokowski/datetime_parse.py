"""Shared ISO-8601 datetime parsing for Linear API fields and tracking payloads."""

from __future__ import annotations

from datetime import UTC, datetime


def parse_linear_iso_datetime(value: str | None) -> datetime | None:
    """Parse a Linear-style ISO-8601 string to an aware UTC ``datetime``.

    Naive strings are treated as UTC. Aware strings are converted to UTC.
    Returns ``None`` if ``value`` is missing, not a string, or unparsable.
    """
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except (ValueError, AttributeError):
        return None
