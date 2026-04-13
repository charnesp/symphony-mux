"""parse_linear_iso_datetime (shared Linear / tracking UTC normalization)."""

from __future__ import annotations

from datetime import UTC, datetime

from stokowski.datetime_parse import parse_linear_iso_datetime


def test_parse_linear_iso_datetime_none_and_empty():
    assert parse_linear_iso_datetime(None) is None
    assert parse_linear_iso_datetime("") is None


def test_parse_linear_iso_datetime_rejects_non_str():
    assert parse_linear_iso_datetime(123) is None  # type: ignore[arg-type]


def test_parse_linear_iso_datetime_z_and_naive_as_utc():
    got = parse_linear_iso_datetime("2026-01-15T12:00:00Z")
    assert got is not None
    assert got.tzinfo == UTC
    assert got.hour == 12

    naive = parse_linear_iso_datetime("2026-01-15T12:00:00")
    assert naive is not None
    assert naive.tzinfo == UTC


def test_parse_linear_iso_datetime_offset_normalized_to_utc():
    got = parse_linear_iso_datetime("2026-01-15T14:00:00+02:00")
    assert got is not None
    assert got == datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


def test_parse_linear_iso_datetime_invalid():
    assert parse_linear_iso_datetime("not-a-date") is None
