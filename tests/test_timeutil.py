#!/usr/bin/env python3
"""Tests for the shared timezone-safe datetime helpers (scrapers/lib/timeutil.py)."""

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

_proj_root = Path(__file__).parent.parent
sys.path.insert(0, str(_proj_root))

from scrapers.lib.timeutil import (  # noqa: E402
    assume_utc,
    parse_naive_ics,
    utc_now,
    utc_today,
    wall_clock,
)


class TestWallClock:
    """wall_clock() constructs naive wall-clock datetimes."""

    def test_constructs_naive_datetime(self):
        result = wall_clock(2026, 3, 14)
        assert isinstance(result, datetime)
        assert result.tzinfo is None
        assert (result.year, result.month, result.day) == (2026, 3, 14)

    def test_preserves_clock_fields(self):
        result = wall_clock(2026, 3, 14, 18, 30)
        assert (result.hour, result.minute) == (18, 30)
        assert result.second == 0

    def test_accepts_full_positional_args(self):
        result = wall_clock(2026, 3, 14, 18, 30, 15)
        assert (result.hour, result.minute, result.second) == (18, 30, 15)

    def test_accepts_unpacked_sequence(self):
        published = (2026, 3, 14, 18, 30, 15)
        result = wall_clock(*published[:6])
        assert (result.year, result.month, result.day, result.hour, result.minute) == (
            2026,
            3,
            14,
            18,
            30,
        )


class TestParseNaiveIcs:
    """parse_naive_ics() parses wall-clock datetime strings without a zone."""

    def test_parses_naive_datetime(self):
        result = parse_naive_ics("2026-03-14 18:30", "%Y-%m-%d %H:%M")
        assert isinstance(result, datetime)
        assert result.tzinfo is None
        assert (result.year, result.month, result.day, result.hour, result.minute) == (
            2026,
            3,
            14,
            18,
            30,
        )

    def test_parses_date_only_format(self):
        result = parse_naive_ics("2026-03-14", "%Y-%m-%d")
        assert result.tzinfo is None
        assert (result.year, result.month, result.day) == (2026, 3, 14)

    def test_raises_value_error_for_bad_input(self):
        with pytest.raises(ValueError):
            parse_naive_ics("not-a-date", "%Y-%m-%d")


class TestUtcNow:
    """utc_now() returns the current absolute instant in UTC."""

    def test_is_timezone_assume_utc(self):
        result = utc_now()
        assert result.tzinfo is not None
        assert result.utcoffset() == UTC.utcoffset(None)

    def test_close_to_now(self):
        from datetime import datetime as dt

        before = dt.now(UTC)
        result = utc_now()
        after = dt.now(UTC)
        assert before <= result <= after


class TestAssumeUtc:
    """assume_utc() treats a naive datetime as UTC and preserves aware values."""

    def test_naive_datetime_is_stamped_utc(self):
        naive = datetime(2026, 3, 14, 18, 30)  # noqa: DTZ001 - deliberately naive input
        result = assume_utc(naive)
        assert result.tzinfo is not None
        assert result.utcoffset() == UTC.utcoffset(None)
        assert (result.hour, result.minute) == (18, 30)

    def test_aware_datetime_is_returned_unchanged(self):
        aware = datetime(2026, 3, 14, 18, 30, tzinfo=UTC)
        assert assume_utc(aware) is aware

    def test_non_utc_aware_datetime_is_preserved(self):
        from datetime import timedelta, timezone

        aware = datetime(2026, 3, 14, 18, 30, tzinfo=timezone(timedelta(hours=-5)))
        result = assume_utc(aware)
        assert result is aware
        assert result.utcoffset() == timedelta(hours=-5)


class TestUtcToday:
    """utc_today() returns today's date in UTC."""

    def test_returns_date_in_utc(self):
        before = utc_now().date()
        result = utc_today()
        after = utc_now().date()
        assert before <= result <= after
