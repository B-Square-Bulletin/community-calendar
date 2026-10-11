#!/usr/bin/env python3
"""Tests for the Sidearm scraper's --home-only filtering (#192).

The HTTP boundary is the module `urlopen` seam: the tests patch it with a small
v3 Calendar payload, so the home / away / neutral decision runs end to end
without touching iuhoosiers.com.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scrapers"))

from scrapers.sidearm import SidearmScraper


def _event(indicator, opponent, at_vs="vs", location=""):
    return {
        "opponent": {"title": opponent, "website": ""},
        "sport": {"title": "Basketball"},
        "locationIndicator": indicator,
        "status": "A",
        "atVs": at_vs,
        "time": "7 p.m.",
        "location": location,
    }


# H = home site, A = away, N = neutral site.
PAYLOAD = [
    {
        "date": "2026-11-01",
        "events": [
            _event("H", "Rutgers", location="Bloomington, Ind."),
            _event("A", "Purdue", at_vs="at", location="West Lafayette, Ind."),
            _event("N", "Arkansas", location="New York, N.Y."),
        ],
    }
]


class _FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode()

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fetch(home_only, payload=PAYLOAD):
    with patch("scrapers.sidearm.urlopen", return_value=_FakeResponse(payload)):
        scraper = SidearmScraper(
            base_url="https://iuhoosiers.com",
            source_name="IU Athletics",
            tz="America/Indiana/Indianapolis",
            home_only=home_only,
        )
        return scraper.fetch_events()


def test_home_only_keeps_only_home_site_games():
    titles = [e["title"] for e in _fetch(home_only=True)]
    assert titles == ["Basketball vs Rutgers"]


def test_home_only_keeps_events_with_unknown_indicator():
    # A missing indicator is not known away/neutral, so keep it.
    payload = [{"date": "2026-11-01", "events": [_event("", "Iowa", location="Bloomington, Ind.")]}]
    titles = [e["title"] for e in _fetch(home_only=True, payload=payload)]
    assert titles == ["Basketball vs Iowa"]


def test_without_home_only_all_sites_are_kept():
    titles = [e["title"] for e in _fetch(home_only=False)]
    assert len(titles) == 3
