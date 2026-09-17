#!/usr/bin/env python3
"""Tests for the base scraper's optional source_url header (#124)."""

import sys
from datetime import datetime
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
