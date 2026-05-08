#!/usr/bin/env python3
"""
Scraper for Knotty Pine Supper Club (Victor, Idaho) live music.

Knotty Pine runs WordPress with the Enfold theme. The /music page renders
each upcoming show inside a `div.avia_textblock` that contains:
    <h1>Artist Name</h1>
    <h3>Day, Month DD, YYYY</h3>
    <p>9pm Door / 10pm Show / 21+<br/>$32 Advanced ...</p>

There is no per-event ticket URL in the page; tickets are sold elsewhere.

Usage:
    python scrapers/knotty_pine.py --output cities/tetonvalley/knotty_pine.ics
"""

import sys
sys.path.insert(0, str(__file__).rsplit('/', 1)[0])

import re
from datetime import datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from lib.base import BaseScraper
from lib.utils import DEFAULT_HEADERS

DATE_RE = re.compile(
    r"^(?:Sun|Mon|Tue|Wed|Thu|Fri|Sat)[a-z]*,\s+"
    r"(?:January|February|March|April|May|June|July|"
    r"August|September|October|November|December)\s+"
    r"\d{1,2},\s+\d{4}$"
)
TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap]m)\s*(door|show)?", re.I)


class KnottyPineScraper(BaseScraper):
    """Scraper for Knotty Pine Supper Club music page."""

    name = "Knotty Pine Supper Club"
    domain = "knottypinesupperclub.com"
    timezone = "America/Denver"

    URL = "https://knottypinesupperclub.com/music/"
    VENUE_LOCATION = "Knotty Pine Supper Club, 58 S Main St, Victor, ID 83455"

    def fetch_events(self) -> list[dict[str, Any]]:
        self.logger.info(f"Fetching {self.URL}")
        resp = requests.get(self.URL, headers=DEFAULT_HEADERS, timeout=30)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        tz = ZoneInfo(self.timezone)
        events: list[dict[str, Any]] = []

        for block in soup.select("div.avia_textblock"):
            h1 = block.find("h1")
            if not h1:
                continue
            title = h1.get_text(strip=True)
            if not title or title.lower() in {"knotty pinemusic", "upcomingshows"}:
                continue

            date_str = self._find_date(block)
            if not date_str:
                self.logger.debug(f"No date for {title!r}, skipping")
                continue

            try:
                event_date = datetime.strptime(date_str, "%A, %B %d, %Y").date()
            except ValueError:
                self.logger.warning(f"Could not parse date {date_str!r} for {title}")
                continue

            paragraph_text = self._first_paragraph_text(block)
            # Some shows pack the times into the date heading rather than a
            # separate <p>; fall back to the whole textblock when needed.
            time_source = paragraph_text or block.get_text(" ", strip=True)
            start_hour, start_minute = self._extract_show_time(time_source)
            dtstart = datetime.combine(
                event_date,
                datetime.min.time().replace(hour=start_hour, minute=start_minute),
                tzinfo=tz,
            )
            dtend = dtstart + timedelta(hours=2, minutes=30)

            events.append({
                "title": title,
                "dtstart": dtstart,
                "dtend": dtend,
                "url": self.URL,
                "location": self.VENUE_LOCATION,
                "description": paragraph_text,
            })

        self.logger.info(f"Parsed {len(events)} events")
        return events

    def _find_date(self, block) -> Optional[str]:
        """
        The date sits in the first heading inside the textblock. Some headings
        also pack additional <br>-separated lines (e.g. "Friday, July 4, 2025
        Free Live Music Barbecue"); pull lines individually and return the
        first that matches the date pattern.
        """
        for tag in block.find_all(["h2", "h3", "h4"]):
            for raw_line in tag.get_text("\n").splitlines():
                line = raw_line.strip()
                if DATE_RE.match(line):
                    return line
        return None

    def _first_paragraph_text(self, block) -> str:
        p = block.find("p")
        if not p:
            return ""
        return p.get_text(" ", strip=True)

    def _extract_show_time(self, text: str) -> tuple[int, int]:
        """
        Pull "10pm Show" if present, otherwise the first time token, otherwise
        default to 8pm. Knotty Pine's pattern is "9pm Door / 10pm Show".
        """
        show_time: Optional[tuple[int, int]] = None
        first_time: Optional[tuple[int, int]] = None

        for match in TIME_RE.finditer(text):
            hour = int(match.group(1)) % 12
            minute = int(match.group(2) or 0)
            if match.group(3).lower() == "pm":
                hour += 12
            label = (match.group(4) or "").lower()
            parsed = (hour, minute)

            if first_time is None:
                first_time = parsed
            if label == "show":
                show_time = parsed
                break

        if show_time:
            return show_time
        if first_time:
            return first_time
        return (20, 0)


if __name__ == "__main__":
    KnottyPineScraper.main()
