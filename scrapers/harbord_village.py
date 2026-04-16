#!/usr/bin/env python3
"""Scraper for Harbord Village Residents' Association yearly calendar."""

from __future__ import annotations

import re
from datetime import date, datetime
from html import unescape
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from lib.base import BaseScraper


MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _clean(text: str) -> str:
    text = unescape(text or "")
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


class HarbordVillageScraper(BaseScraper):
    name = "Harbord Village Residents' Association"
    domain = "harbordvillage.com"
    timezone = "America/Toronto"
    page_url = "https://harbordvillage.com/calendar-of-hvra-events-for-2026/"
    default_url = page_url
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; CommunityCalendar/1.0)",
        "Accept": "text/html,application/xhtml+xml",
    }

    def fetch_html(self) -> str:
        req = Request(self.page_url, headers=self.headers)
        with urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8")

    def parse_date_cell(self, text: str, year: int) -> date | None:
        text = _clean(text).replace("(new date)", "").strip()
        m = re.search(r"([A-Za-z]+)\.?\s+([A-Za-z]+)\.?\s+(\d{1,2})", text)
        if not m:
            return None
        month = MONTHS.get(m.group(2).lower()[:3])
        day = int(m.group(3))
        if not month:
            return None
        return date(year, month, day)

    def parse_times(self, text: str) -> tuple[tuple[int, int], tuple[int, int]] | None:
        m = re.search(
            r"(\d{1,2})(?::(\d{2}))?\s*-\s*(\d{1,2})(?::(\d{2}))?\s*pm",
            text,
            re.I,
        )
        if not m:
            return None
        start_hour = int(m.group(1))
        start_minute = int(m.group(2) or 0)
        end_hour = int(m.group(3))
        end_minute = int(m.group(4) or 0)
        if start_hour != 12:
            start_hour += 12
        if end_hour != 12:
            end_hour += 12
        return (start_hour, start_minute), (end_hour, end_minute)

    def fetch_events(self) -> list[dict]:
        html = self.fetch_html()
        soup = BeautifulSoup(html, "html.parser")
        year_match = re.search(r"Calendar of HVRA events for (\d{4})", html)
        year = int(year_match.group(1)) if year_match else datetime.now().year
        tz = ZoneInfo(self.timezone)
        today = datetime.now(tz).date()
        rows = soup.select("tbody tr")
        events = []

        for row in rows:
            cells = row.find_all("td")
            if len(cells) != 3:
                continue

            date_text = _clean(cells[0].get_text(" ", strip=True))
            event_text = _clean(cells[1].get_text(" ", strip=True))
            location = _clean(cells[2].get_text(" ", strip=True))

            day = self.parse_date_cell(date_text, year)
            if not day or event_text.lower().startswith("tba:"):
                continue

            if "all evening" in event_text.lower():
                dtstart = day
                dtend = day
            else:
                parsed_times = self.parse_times(event_text)
                if parsed_times:
                    (start_hour, start_minute), (end_hour, end_minute) = parsed_times
                    dtstart = datetime(day.year, day.month, day.day, start_hour, start_minute, tzinfo=tz)
                    dtend = datetime(day.year, day.month, day.day, end_hour, end_minute, tzinfo=tz)
                else:
                    dtstart = day
                    dtend = day

            compare_day = dtstart.date() if isinstance(dtstart, datetime) else dtstart
            if compare_day < today:
                continue

            title = event_text.split(",")[0].strip()
            description = f"From the published HVRA yearly calendar. Full listing: {event_text}."
            uid_slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")

            events.append(
                {
                    "title": title,
                    "dtstart": dtstart,
                    "dtend": dtend,
                    "url": self.page_url,
                    "location": location,
                    "description": description,
                    "uid": f"hvra-{day.isoformat()}-{uid_slug}@{self.domain}",
                }
            )

        return events


if __name__ == "__main__":
    HarbordVillageScraper.main()
