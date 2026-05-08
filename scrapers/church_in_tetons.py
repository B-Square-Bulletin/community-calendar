#!/usr/bin/env python3
"""
Scraper for Church in the Tetons (Driggs, Idaho).

Church in the Tetons runs WordPress with the **ezChurch / ChurchDev** plugin.
Each upcoming event renders as `<article class="events-archive">` containing:

    <div class="event-list-date">
        <p>Thursday<br>April 30</p>
    </div>
    <div class="event-list-time">6:00 pm - 7:00 pm</div>
    <div class="event-list-title"><a href="...">Event Title</a></div>
    <div class="event-list-details"> ...summary... </div>

The page omits the year in the date string, so we infer it from the displayed
day-of-week (defaulting to the current calendar year and rolling forward when
that date is more than 30 days in the past).

Usage:
    python scrapers/church_in_tetons.py \\
        --output cities/tetonvalley/church_in_tetons.ics
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

MONTHS = (
    "January February March April May June "
    "July August September October November December"
).split()

TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap]m)", re.I)


class ChurchInTetonsScraper(BaseScraper):
    """Scraper for Church in the Tetons (ezChurch)."""

    name = "Church in the Tetons"
    domain = "churchinthetetons.org"
    timezone = "America/Denver"

    URL = "https://www.churchinthetetons.org/events/"
    DEFAULT_LOCATION = "Church in the Tetons, 60 South Main St, Driggs, ID 83422"

    def fetch_events(self) -> list[dict[str, Any]]:
        self.logger.info(f"Fetching {self.URL}")
        resp = requests.get(self.URL, headers=DEFAULT_HEADERS, timeout=30)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        tz = ZoneInfo(self.timezone)
        now = datetime.now(tz)

        events: list[dict[str, Any]] = []
        for article in soup.find_all("article", class_="events-archive"):
            parsed = self._parse_article(article, now, tz)
            if parsed:
                events.append(parsed)

        self.logger.info(f"Parsed {len(events)} events")
        return events

    def _parse_article(self, article, now: datetime, tz: ZoneInfo) -> Optional[dict[str, Any]]:
        title_el = article.select_one(".event-list-title")
        if not title_el:
            return None
        title = title_el.get_text(" ", strip=True)
        if not title:
            return None

        date_el = article.select_one(".event-list-date")
        if not date_el:
            return None
        day_name, month_name, day_num = self._parse_date_text(date_el)
        if not month_name or not day_num:
            return None

        time_el = article.select_one(".event-list-time")
        start_time, end_time = self._parse_time_range(
            time_el.get_text(" ", strip=True) if time_el else ""
        )

        event_date = self._infer_date(day_name, month_name, day_num, now)
        dtstart = datetime.combine(
            event_date,
            datetime.min.time().replace(hour=start_time[0], minute=start_time[1]),
            tzinfo=tz,
        )
        if end_time:
            dtend = datetime.combine(
                event_date,
                datetime.min.time().replace(hour=end_time[0], minute=end_time[1]),
                tzinfo=tz,
            )
            if dtend < dtstart:
                dtend += timedelta(days=1)
        else:
            dtend = dtstart + timedelta(hours=1)

        link_el = article.select_one(".event-list-title a") or article.find(
            "a", string=lambda s: s and "Learn More" in s
        )
        url = link_el.get("href") if link_el else self.URL

        details_el = article.select_one(".event-list-details")
        description = details_el.get_text(" ", strip=True) if details_el else ""
        # When there's no description body, ezChurch fills .event-list-details
        # with the navigation labels alone — drop those.
        if description in {"Save the Date Learn More", "Save the Date", "Learn More"}:
            description = ""

        return {
            "title": title,
            "dtstart": dtstart,
            "dtend": dtend,
            "url": url,
            "location": self.DEFAULT_LOCATION,
            "description": description,
        }

    def _parse_date_text(self, date_el) -> tuple[Optional[str], Optional[str], Optional[int]]:
        """Parse 'Thursday\\nApril 30' into ('Thursday', 'April', 30)."""
        lines = [l.strip() for l in date_el.get_text("\n").splitlines() if l.strip()]
        if not lines:
            return None, None, None

        day_name: Optional[str] = None
        month_name: Optional[str] = None
        day_num: Optional[int] = None

        for line in lines:
            if not day_name and line.split()[0] in {
                "Sunday", "Monday", "Tuesday", "Wednesday",
                "Thursday", "Friday", "Saturday",
            }:
                day_name = line.split()[0]
                continue
            m = re.match(r"([A-Z][a-z]+)\s+(\d{1,2})", line)
            if m and m.group(1) in MONTHS:
                month_name = m.group(1)
                day_num = int(m.group(2))
        return day_name, month_name, day_num

    def _parse_time_range(self, text: str) -> tuple[tuple[int, int], Optional[tuple[int, int]]]:
        """Parse '6:00 pm - 7:00 pm' or '7:01 pm' into (start, end?)."""
        times: list[tuple[int, int]] = []
        for m in TIME_RE.finditer(text):
            hour = int(m.group(1)) % 12
            minute = int(m.group(2) or 0)
            if m.group(3).lower() == "pm":
                hour += 12
            times.append((hour, minute))
        if not times:
            return (12, 0), None
        if len(times) >= 2:
            return times[0], times[1]
        return times[0], None

    def _infer_date(self, day_name: Optional[str], month_name: str,
                    day_num: int, now: datetime):
        """
        Find the date that matches `month_name day_num` and the optional
        weekday hint, starting from the current year and rolling forward up
        to two years if needed.
        """
        month_num = MONTHS.index(month_name) + 1
        for year in (now.year, now.year + 1, now.year + 2):
            try:
                candidate = datetime(year, month_num, day_num).date()
            except ValueError:
                continue
            if day_name and candidate.strftime("%A") != day_name:
                continue
            # Reject anything more than 30 days in the past
            if (now.date() - candidate).days > 30:
                continue
            return candidate
        # Last resort: take the first valid date even if weekday mismatched
        return datetime(now.year, month_num, day_num).date()


if __name__ == "__main__":
    ChurchInTetonsScraper.main()
