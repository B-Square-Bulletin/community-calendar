#!/usr/bin/env python3
"""
Scraper for Holy Trinity Catholic Church's concert series page.

The official page at https://trinity.org/concerts contains an "Upcoming Concerts"
content block rendered in static HTML. Each upcoming event appears as a paragraph
with title, date, concert time, and optional detail link.
"""

import sys
sys.path.insert(0, str(__file__).rsplit('/', 1)[0])

import re
from datetime import datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag

from lib.base import BaseScraper


PAGE_URL = "https://trinity.org/concerts"
LOCATION = "Holy Trinity Catholic Church, 1315 36th Street NW, Washington, DC 20007"

DATE_RE = re.compile(
    r'(?P<weekday>Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+'
    r'(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2}),\s+(?P<year>\d{4})'
)
TIME_RE = re.compile(r'concert time\s*(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*(?P<ampm>am|pm)', re.I)
DOORS_RE = re.compile(r'doors? (?:open at|,)\s*(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*(?P<ampm>am|pm)', re.I)


class HolyTrinityConcertsScraper(BaseScraper):
    name = "Holy Trinity Concerts"
    domain = "trinity.org"
    timezone = "America/New_York"
    default_url = PAGE_URL

    def fetch_events(self) -> list[dict[str, Any]]:
        html = self.fetch_text_with_curl(PAGE_URL, accept="text/html")
        soup = BeautifulSoup(html, "html.parser")
        upcoming = self._find_upcoming_block(soup)
        if upcoming is None:
            self.logger.warning("Could not find Upcoming Concerts block")
            return []

        tz = ZoneInfo(self.timezone)
        now = datetime.now(tz)
        events: list[dict[str, Any]] = []

        for paragraph in upcoming.find_all("p", recursive=False):
            event = self._parse_paragraph(paragraph, tz, now)
            if event:
                events.append(event)

        return events

    def _find_upcoming_block(self, soup: BeautifulSoup) -> Optional[Tag]:
        header = soup.find("h3", string=lambda s: s and "Upcoming Concerts" in s)
        if not header:
            return None
        return header.find_next("div", class_="siteorigin-widget-tinymce")

    def _parse_paragraph(
        self,
        paragraph: Tag,
        tz: ZoneInfo,
        now: datetime,
    ) -> Optional[dict[str, Any]]:
        text = paragraph.get_text(" ", strip=True)
        if not text:
            return None

        date_match = DATE_RE.search(text)
        time_match = TIME_RE.search(text)
        if not (date_match and time_match):
            return None

        dtstart = self._build_datetime(date_match, time_match, tz)
        if dtstart < now - timedelta(hours=4):
            return None

        title = self._extract_title(paragraph)
        if not title:
            return None

        dtend = dtstart + timedelta(hours=2)
        doors_match = DOORS_RE.search(text)
        description_parts = []
        if doors_match:
            doors_time = self._format_time_match(doors_match)
            description_parts.append(f"Doors open: {doors_time}")

        clean_text = " ".join(text.split())
        if clean_text:
            description_parts.append(clean_text)

        link = self._extract_link(paragraph)

        return {
            "title": title,
            "dtstart": dtstart,
            "dtend": dtend,
            "url": link or PAGE_URL,
            "location": LOCATION,
            "description": " | ".join(description_parts),
        }

    @staticmethod
    def _extract_title(paragraph: Tag) -> str:
        anchor = paragraph.find("a")
        if anchor:
            title = anchor.get_text(" ", strip=True)
            if title:
                return title

        bold = paragraph.find(["b", "strong"])
        if bold:
            title = bold.get_text(" ", strip=True)
            if title:
                return title

        return ""

    @staticmethod
    def _extract_link(paragraph: Tag) -> str:
        anchors = paragraph.find_all("a")
        for anchor in anchors:
            href = (anchor.get("href") or "").strip()
            text = anchor.get_text(" ", strip=True)
            if href and text:
                return href
        return ""

    @staticmethod
    def _build_datetime(date_match: re.Match[str], time_match: re.Match[str], tz: ZoneInfo) -> datetime:
        month = date_match.group("month")
        day = int(date_match.group("day"))
        year = int(date_match.group("year"))
        hour = int(time_match.group("hour")) % 12
        if time_match.group("ampm").lower() == "pm":
            hour += 12
        minute = int(time_match.group("minute"))
        return datetime.strptime(f"{month} {day} {year}", "%B %d %Y").replace(
            hour=hour,
            minute=minute,
            tzinfo=tz,
        )

    @staticmethod
    def _format_time_match(match: re.Match[str]) -> str:
        hour = int(match.group("hour"))
        minute = int(match.group("minute"))
        ampm = match.group("ampm").lower()
        return f"{hour}:{minute:02d}{ampm}"


if __name__ == "__main__":
    HolyTrinityConcertsScraper.main()
