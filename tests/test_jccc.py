#!/usr/bin/env python3
"""Tests for the JCCC event-currency check's date/datetime comparisons."""

import sys
from datetime import datetime, timedelta
from pathlib import Path

_proj_root = Path(__file__).parent.parent
sys.path.insert(0, str(_proj_root))
sys.path.insert(0, str(_proj_root / "scrapers"))

from scrapers.jccc import JCCCScraper  # noqa: E402


class TestEventIsCurrentOrFuture:
    def setup_method(self):
        self.scraper = JCCCScraper()
        self.today = datetime.now(self.scraper.tz).date()

    def test_date_start_with_datetime_end_compares_without_raising(self):
        # A datetime `dtend` under a date `dtstart` used to compare a datetime
        # to a date, which raises TypeError at runtime.
        tomorrow = self.today + timedelta(days=1)
        assert self.scraper.event_is_current_or_future(
            tomorrow, datetime.combine(tomorrow, datetime.min.time())
        )

    def test_date_range_ending_today_is_not_current(self):
        assert not self.scraper.event_is_current_or_future(self.today, self.today)

    def test_date_range_ending_yesterday_is_past(self):
        yesterday = self.today - timedelta(days=1)
        assert not self.scraper.event_is_current_or_future(yesterday, yesterday)

    def test_datetime_range_in_the_future_is_current(self):
        start = datetime.now(self.scraper.tz) + timedelta(days=2)
        assert self.scraper.event_is_current_or_future(start, start + timedelta(hours=2))
