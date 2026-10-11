#!/usr/bin/env python3
"""Tests for the FAR Center scraper's event UID and date parsing."""

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

# Add project root and scrapers/ to path so scraper imports resolve
_proj_root = Path(__file__).parent.parent
sys.path.insert(0, str(_proj_root))
sys.path.insert(0, str(_proj_root / "scrapers"))

from scrapers.far_center import FARCenterScraper  # noqa: E402

TZ = ZoneInfo("America/Indiana/Indianapolis")
NOW = datetime(2026, 10, 10, tzinfo=TZ)


def _card(title: str, href: str, date_line: str = "Sunday, October 11 | 2:00pm - 5:00pm") -> str:
    return f"""
    <div class="mb-8">
      <h3><a href="{href}">{title}</a></h3>
      <p class="text-sm mb-1">A description.</p>
      <p class="text-sm mb-1">{date_line}</p>
    </div>
    """


def _parse(html: str) -> dict:
    card = BeautifulSoup(html, "html.parser").select_one("div.mb-8")
    assert card is not None
    event = FARCenterScraper()._parse_card(card, TZ, NOW)
    assert event is not None
    return event


def test_uid_is_stable_across_runs():
    href = "https://www.thefar.org/events/event/122918/"
    first = _parse(_card("Photo Forward", href))
    second = _parse(_card("Photo Forward", href))
    assert first["uid"] == second["uid"]


def test_distinct_events_do_not_collide():
    # Same day, titles sharing the first 40 characters: the old title slug
    # collapsed these to one UID.
    title = "Bloomington Photography Exhibition " + "X" * 20
    a = _parse(_card(title, "https://www.thefar.org/events/event/111111/"))
    b = _parse(_card(title, "https://www.thefar.org/events/event/222222/"))
    assert a["uid"] != b["uid"]


def test_uid_falls_back_when_url_has_no_id():
    event = _parse(_card("Photo Review", "https://www.thefar.org/events/list"))
    assert event["uid"].endswith("@thefar.org")


def test_next_year_date_rolls_forward():
    # Seen in October, a January date belongs to the next year.
    dtstart, _ = FARCenterScraper()._parse_datetime("January 20", TZ, NOW)
    assert dtstart is not None
    assert (dtstart.year, dtstart.month, dtstart.day) == (2027, 1, 20)


def test_same_year_date_is_unchanged():
    dtstart, _ = FARCenterScraper()._parse_datetime("November 5", TZ, NOW)
    assert dtstart is not None
    assert dtstart.year == 2026


def test_multi_day_range_crosses_new_year():
    # The end date belongs to the next year, not the start date's year.
    dtstart, dtend = FARCenterScraper()._parse_datetime(
        "December 30 8:00pm - January 2 10:00pm", TZ, NOW
    )
    assert dtstart is not None and dtend is not None
    assert dtstart == datetime(2026, 12, 30, 20, 0, tzinfo=TZ)
    assert dtend == datetime(2027, 1, 2, 22, 0, tzinfo=TZ)
