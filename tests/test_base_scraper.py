#!/usr/bin/env python3
"""Tests for the base scraper's optional source_url header (#124)."""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Add project root to path so scraper imports resolve
sys.path.insert(0, str(Path(__file__).parent.parent))

from scrapers.lib.base import BaseScraper

TZ = ZoneInfo("America/Indiana/Indianapolis")


class _Scraper(BaseScraper):
    name = "Test Source"
    domain = "example.com"
    timezone = "America/Indiana/Indianapolis"

    def fetch_events(self):
        return []


class _ScraperWithSourceUrl(_Scraper):
    source_url = "https://www.visitbloomington.com/events/"


def _sample_event() -> dict[str, object]:
    return {
        "title": "Test Event",
        "dtstart": datetime(2026, 7, 15, 19, 0, tzinfo=TZ),
        "dtend": datetime(2026, 7, 15, 21, 0, tzinfo=TZ),
    }


class TestSourceUrlHeader:
    """A subclass that sets source_url stamps X-SOURCE-URL on every VEVENT.

    X-SOURCE-URL is the source page for an event. ics_to_json.py already reads
    it as the fallback event URL, so emitting it from the base class lets a
    scraper point at its source without special-casing the JSON stage.
    """

    def test_source_url_set_emits_header(self):
        cal = _ScraperWithSourceUrl().create_calendar([_sample_event()])
        ics = cal.to_ical().decode()
        assert "X-SOURCE-URL:https://www.visitbloomington.com/events/" in ics

    def test_source_url_unset_omits_header(self):
        cal = _Scraper().create_calendar([_sample_event()])
        ics = cal.to_ical().decode()
        assert "X-SOURCE-URL" not in ics


class TestGeo:
    """A `geo` (lat, lng) on an event dict becomes an ICS GEO property."""

    def test_geo_set_emits_geostamp(self):
        event = _sample_event()
        event["geo"] = (39.168585, -86.517361)
        ics = _Scraper().create_calendar([event]).to_ical().decode()
        assert "GEO:39.168585;-86.517361" in ics

    def test_geo_unset_omits_geostamp(self):
        ics = _Scraper().create_calendar([_sample_event()]).to_ical().decode()
        assert "GEO:" not in ics


class _FixedEventsScraper(_Scraper):
    """A scraper whose fetch_events() returns a fixed set, for run() tests."""

    def __init__(self, events):
        super().__init__()
        self._events = events

    def fetch_events(self):
        return self._events


class TestRunHorizonFilter:
    """run() drops events beyond the Horizon, reading dates and datetimes alike."""

    def _run_ics(self, tmp_path, events) -> str:
        scraper = _FixedEventsScraper(events)
        scraper.months_ahead = 1  # a 31-day Horizon
        out = tmp_path / "cal.ics"
        scraper.run(str(out))
        return out.read_text()

    def test_drops_an_event_beyond_the_horizon(self, tmp_path):
        now = datetime.now(TZ)
        events = [
            {"title": "Within", "dtstart": now + timedelta(days=10)},
            {"title": "Beyond", "dtstart": now + timedelta(days=40)},
        ]
        ics = self._run_ics(tmp_path, events)

        assert "Within" in ics
        assert "Beyond" not in ics

    def test_keeps_a_date_event_inside_the_horizon(self, tmp_path):
        events = [{"title": "Date Event", "dtstart": datetime.now(TZ).date() + timedelta(days=5)}]
        ics = self._run_ics(tmp_path, events)

        assert "Date Event" in ics

    def test_drops_an_event_without_a_start(self, tmp_path):
        events = [{"title": "No Start"}]
        ics = self._run_ics(tmp_path, events)

        assert "No Start" not in ics
