#!/usr/bin/env python3
"""Tests for the Horizon boundary and its predicate (scrapers/lib/horizon.py).

The Horizon is the end of the prefetched event set. `horizon_end` fixes the
boundary instant; `within` answers "is this event inside it?", normalising the
`date` / naive-datetime / aware-datetime shapes scraper events arrive in.
"""

import sys
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_proj_root = Path(__file__).parent.parent
sys.path.insert(0, str(_proj_root))

from scrapers.lib.horizon import horizon_end, within  # noqa: E402
from scrapers.lib.timeutil import wall_clock  # noqa: E402

TZ = ZoneInfo("America/Indiana/Indianapolis")


class TestHorizonEnd:
    """horizon_end() is the single definition of the boundary instant."""

    def test_adds_months_ahead_times_31_days(self):
        now = datetime(2026, 1, 1, tzinfo=TZ)
        assert horizon_end(now, 3) == datetime(2026, 4, 4, tzinfo=TZ)

    def test_preserves_the_requested_clock_zone(self):
        now = datetime(2026, 1, 1, tzinfo=TZ)
        assert horizon_end(now, 6).tzinfo == TZ

    def test_without_now_returns_an_aware_instant_ahead_of_today(self):
        end = horizon_end(None, 3)
        assert end.tzinfo is not None
        assert end > datetime.now(end.tzinfo)


class TestWithin:
    """within() compares a scraper event's date/datetime against the boundary."""

    def test_date_before_the_boundary_is_within(self):
        end = datetime(2026, 4, 4, 12, 0, tzinfo=TZ)
        assert within(date(2026, 4, 4), end) is True

    def test_a_past_date_is_within(self):
        # within() is an upper bound only: past events are not beyond the
        # Horizon, matching run()'s filter, which never drops them.
        end = datetime(2026, 4, 4, 12, 0, tzinfo=TZ)
        assert within(date(2026, 1, 1), end) is True

    def test_the_boundary_day_is_inclusive(self):
        end = datetime(2026, 4, 4, tzinfo=TZ)
        assert within(date(2026, 4, 4), end) is True

    def test_date_after_the_boundary_is_not_within(self):
        end = datetime(2026, 4, 4, 12, 0, tzinfo=TZ)
        assert within(date(2026, 4, 5), end) is False

    def test_naive_datetime_is_read_in_the_boundarys_zone(self):
        end = datetime(2026, 4, 4, 12, 0, tzinfo=TZ)
        assert within(wall_clock(2026, 4, 4, 11, 0), end) is True
        assert within(wall_clock(2026, 4, 4, 13, 0), end) is False

    def test_aware_datetime_compares_as_an_absolute_instant(self):
        end = datetime(2026, 4, 4, 12, 0, tzinfo=TZ)  # 16:00 UTC in April
        assert within(datetime(2026, 4, 4, 16, 0, tzinfo=UTC), end) is True
        assert within(datetime(2026, 4, 4, 16, 1, tzinfo=UTC), end) is False

    def test_missing_start_is_not_within(self):
        assert within(None, datetime(2026, 4, 4, tzinfo=TZ)) is False
