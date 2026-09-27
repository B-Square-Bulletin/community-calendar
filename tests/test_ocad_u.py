#!/usr/bin/env python3
"""Tests for the OCAD University scraper's embedded-calendar parsing.

``parse_calendar_payload`` decodes a base64 ``data:text/calendar`` link and
reads DTSTART/DTEND off the first VEVENT. That is the codebase's only
``Component.decoded()`` call site, so this locks its behaviour under the
icalendar 7.x return-type change (issue #161).
"""

import base64
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add project root and scrapers/ to path so scraper imports resolve
_proj_root = Path(__file__).parent.parent
sys.path.insert(0, str(_proj_root))
sys.path.insert(0, str(_proj_root / "scrapers"))

from bs4 import BeautifulSoup  # noqa: E402

from scrapers.ocad_u import OCADUScraper  # noqa: E402

VEVENT = (
    "BEGIN:VCALENDAR\r\n"
    "VERSION:2.0\r\n"
    "BEGIN:VEVENT\r\n"
    "SUMMARY:Exhibition Opening\r\n"
    "UID:opening@ocadu.ca\r\n"
    "DTSTART:20260715T180000Z\r\n"
    "DTEND:20260715T200000Z\r\n"
    "END:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)


def _detail_with_calendar_link(ics: str) -> BeautifulSoup:
    payload = base64.b64encode(ics.encode("utf-8")).decode("ascii")
    html = (
        "<html><body>"
        f'<a href="data:text/calendar;charset=utf-8;base64,{payload}">Add to calendar</a>'
        "</body></html>"
    )
    return BeautifulSoup(html, "html.parser")


class TestParseCalendarPayload:
    """``decoded()`` returns datetimes for DTSTART/DTEND under icalendar 7.x."""

    def test_returns_the_event_datetimes(self):
        soup = _detail_with_calendar_link(VEVENT)

        dtstart, dtend = OCADUScraper().parse_calendar_payload(soup)

        assert dtstart == datetime(2026, 7, 15, 18, 0, tzinfo=UTC)
        assert dtend == datetime(2026, 7, 15, 20, 0, tzinfo=UTC)

    def test_no_calendar_link_returns_none_pair(self):
        soup = BeautifulSoup("<html><body><h1>Event</h1></body></html>", "html.parser")

        assert OCADUScraper().parse_calendar_payload(soup) == (None, None)
