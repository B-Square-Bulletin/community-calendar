#!/usr/bin/env python3
"""
Scraper for Dumbarton Concerts' official season page.

The current season lives on a static Squarespace page with one text block per
concert followed by a "More information and tickets" button block. We parse
titles, blurbs, dates, times, and the linked per-concert detail page directly
from that official page.
"""

import sys
sys.path.insert(0, str(__file__).rsplit('/', 1)[0])

from datetime import datetime, timedelta
import re
from typing import Any, Optional
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag

from lib.base import BaseScraper


PAGE_URL = "https://dumbartonconcerts.org/26-27-tickets"
SITE_URL = "https://dumbartonconcerts.org"
LOCATION = "Historic Dumbarton Church, 3133 Dumbarton Street NW, Washington, DC 20007"

DATE_RE = re.compile(
    r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
    r"([A-Z][a-z]+)\s+(\d{1,2}),\s+(\d{4})"
)
TIME_PAIR_RE = re.compile(r"(\d{1,2}:\d{2})\s+and\s+(\d{1,2}:\d{2})\s+([ap])\.m\.", re.I)
TIME_RE = re.compile(r"(\d{1,2}:\d{2})\s*([ap])\.m\.", re.I)


class DumbartonConcertsScraper(BaseScraper):
    name = "Dumbarton Concerts"
    domain = "dumbartonconcerts.org"
    timezone = "America/New_York"
    default_url = PAGE_URL

    def fetch_events(self) -> list[dict[str, Any]]:
        html = self.fetch_text_with_curl(PAGE_URL, accept="text/html")
        soup = BeautifulSoup(html, "html.parser")
        blocks = soup.select("div.sqs-block.html-block")
        self.logger.info(f"Found {len(blocks)} html blocks on season page")

        tz = ZoneInfo(self.timezone)
        now = datetime.now(tz)
        events: list[dict[str, Any]] = []

        for block in blocks:
            for event in self._parse_block(block, tz, now):
                events.append(event)

        events.sort(key=lambda e: e["dtstart"])
        return events

    def _parse_block(self, block: Tag, tz: ZoneInfo, now: datetime) -> list[dict[str, Any]]:
        content = block.select_one("div.sqs-html-content")
        if content is None:
            return []

        title_el = content.find("h2")
        if title_el is None:
            return []

        title = self._clean_text(title_el.get_text(" ", strip=True))
        if not title or title.startswith("I would like to make") or "membership here" in title.lower():
            return []

        dates_text = self._extract_dates_text(content)
        if not dates_text or not DATE_RE.search(dates_text):
            return []

        dates = self._extract_dates(dates_text)
        times = self._extract_times(dates_text)
        if not dates or not times:
            return []

        detail_url = self._extract_detail_url(block)
        subtitle = self._extract_subtitle(content)
        pricing = self._extract_pricing(dates_text)
        description = " | ".join(part for part in [subtitle, pricing] if part)

        events: list[dict[str, Any]] = []
        for dtstart in self._expand_datetimes(dates, times, tz):
            if dtstart < now - timedelta(hours=4):
                continue
            events.append({
                "title": title,
                "dtstart": dtstart,
                "dtend": dtstart + timedelta(hours=2),
                "url": detail_url or PAGE_URL,
                "location": LOCATION,
                "description": description,
            })

        return events

    @staticmethod
    def _clean_text(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    def _extract_dates_text(self, content: Tag) -> str:
        for paragraph in content.find_all("p"):
            text = paragraph.get_text("\n", strip=True)
            if DATE_RE.search(text):
                return self._clean_text(text.replace("\n", " "))
        return ""

    def _extract_subtitle(self, content: Tag) -> str:
        first_p = content.find("p")
        if not first_p:
            return ""
        text = self._clean_text(first_p.get_text(" ", strip=True))
        return text

    def _extract_pricing(self, dates_text: str) -> str:
        idx = dates_text.find("$")
        if idx != -1:
            return dates_text[idx:].strip()
        return ""

    @staticmethod
    def _extract_dates(dates_text: str) -> list[tuple[str, int, int]]:
        dates: list[tuple[str, int, int]] = []
        for _, month, day, year in DATE_RE.findall(dates_text):
            dates.append((month, int(day), int(year)))
        return dates

    @staticmethod
    def _extract_times(dates_text: str) -> list[tuple[int, int]]:
        pair_match = TIME_PAIR_RE.search(dates_text)
        if pair_match:
            ampm = pair_match.group(3).lower()
            return [
                DumbartonConcertsScraper._parse_time(pair_match.group(1), ampm),
                DumbartonConcertsScraper._parse_time(pair_match.group(2), ampm),
            ]

        match = TIME_RE.search(dates_text)
        if match:
            return [DumbartonConcertsScraper._parse_time(match.group(1), match.group(2).lower())]

        return []

    @staticmethod
    def _parse_time(time_text: str, ampm: str) -> tuple[int, int]:
        hour, minute = [int(part) for part in time_text.split(":", 1)]
        hour %= 12
        if ampm == "p":
            hour += 12
        return hour, minute

    @staticmethod
    def _expand_datetimes(
        dates: list[tuple[str, int, int]],
        times: list[tuple[int, int]],
        tz: ZoneInfo,
    ) -> list[datetime]:
        datetimes: list[datetime] = []
        for month, day, year in dates:
            base = datetime.strptime(f"{month} {day} {year}", "%B %d %Y")
            for hour, minute in times:
                datetimes.append(base.replace(hour=hour, minute=minute, tzinfo=tz))
        return datetimes

    def _extract_detail_url(self, block: Tag) -> str:
        sibling = block.find_next_sibling()
        while sibling is not None:
            classes = sibling.get("class", [])
            if "button-block" in classes:
                link = sibling.find("a", href=True)
                if link:
                    return urljoin(SITE_URL, link["href"])
                return ""
            if "html-block" in classes:
                return ""
            sibling = sibling.find_next_sibling()
        return ""


if __name__ == "__main__":
    DumbartonConcertsScraper.main()
