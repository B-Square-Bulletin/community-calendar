#!/usr/bin/env python3
"""Scraper for Waterfront BIA public events."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from html import unescape
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from lib.base import BaseScraper


MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _clean(text: str) -> str:
    text = unescape(text or "")
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


class WaterfrontBIAScraper(BaseScraper):
    name = "Waterfront BIA"
    domain = "waterfrontbia.com"
    timezone = "America/Toronto"
    sitemap_url = "https://waterfrontbia.com/sitemap.xml"
    default_url = "https://waterfrontbia.com/events/"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; CommunityCalendar/1.0)",
        "Accept": "text/html,application/xhtml+xml,application/xml",
    }

    def fetch_url(self, url: str) -> str:
        req = Request(url, headers=self.headers)
        with urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", "ignore")

    def fetch_event_urls(self) -> list[str]:
        xml_text = self.fetch_url(self.sitemap_url)
        root = ET.fromstring(xml_text)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = []
        for loc in root.findall("sm:url/sm:loc", ns):
            url = (loc.text or "").strip()
            if "/events/" in url and not url.endswith("/events"):
                urls.append(url)
        return sorted(set(urls))

    def parse_date_range(self, text: str, today: date) -> tuple[date, date] | tuple[None, None]:
        text = _clean(text)
        same_month = re.match(r"([A-Za-z]+)\s+(\d{1,2})\s*(?:&|-|to)\s*(\d{1,2})$", text, re.I)
        if same_month:
            month = MONTHS.get(same_month.group(1).lower())
            start_day = int(same_month.group(2))
            end_day = int(same_month.group(3))
            year = today.year
            start = date(year, month, start_day)
            end = date(year, month, end_day)
            if end < today - timedelta(days=30):
                start = date(year + 1, month, start_day)
                end = date(year + 1, month, end_day)
            return start, end

        cross_month = re.match(
            r"([A-Za-z]+)\s+(\d{1,2})\s*(?:-|to)\s*([A-Za-z]+)\s+(\d{1,2})$",
            text,
            re.I,
        )
        if cross_month:
            start_month = MONTHS.get(cross_month.group(1).lower())
            start_day = int(cross_month.group(2))
            end_month = MONTHS.get(cross_month.group(3).lower())
            end_day = int(cross_month.group(4))
            year = today.year
            start = date(year, start_month, start_day)
            end = date(year, end_month, end_day)
            if end < today - timedelta(days=30):
                start = date(year + 1, start_month, start_day)
                end = date(year + 1, end_month, end_day)
            return start, end

        single = re.match(r"([A-Za-z]+)\s+(\d{1,2})$", text, re.I)
        if single:
            month = MONTHS.get(single.group(1).lower())
            day = int(single.group(2))
            year = today.year
            start = date(year, month, day)
            if start < today - timedelta(days=30):
                start = date(year + 1, month, day)
            return start, start

        return None, None

    def parse_time_range(self, text: str) -> tuple[tuple[int, int], tuple[int, int]] | None:
        text = _clean(text).replace("–", "-")
        both = re.match(
            r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\s*-\s*(\d{1,2})(?::(\d{2}))?\s*(AM|PM)",
            text,
            re.I,
        )
        if both:
            sh, sm, sap, eh, em, eap = both.groups()
            return self._to_24h(int(sh), int(sm or 0), sap), self._to_24h(int(eh), int(em or 0), eap)

        one = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)$", text, re.I)
        if one:
            sh, sm, sap = one.groups()
            start = self._to_24h(int(sh), int(sm or 0), sap)
            end_dt = datetime(2000, 1, 1, start[0], start[1]) + timedelta(hours=2)
            return start, (end_dt.hour, end_dt.minute)

        return None

    def _to_24h(self, hour: int, minute: int, ampm: str) -> tuple[int, int]:
        ampm = ampm.lower()
        if ampm == "pm" and hour != 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        return hour, minute

    def extract_labeled_value(self, strings: list[str], label: str) -> str:
        try:
            idx = strings.index(label)
        except ValueError:
            return ""
        if idx + 1 < len(strings):
            return strings[idx + 1]
        return ""

    def parse_event_page(self, url: str) -> dict | None:
        html = self.fetch_url(url)
        if 'id="__next_error__"' in html or 'NEXT_NOT_FOUND' in html:
            return None

        soup = BeautifulSoup(html, "html.parser")
        strings = [_clean(s) for s in soup.stripped_strings if _clean(s)]
        if not strings:
            return None

        title = _clean(soup.find("meta", property="og:title").get("content", "")) if soup.find("meta", property="og:title") else strings[0]
        description = _clean(soup.find("meta", attrs={"name": "description"}).get("content", "")) if soup.find("meta", attrs={"name": "description"}) else ""
        date_text = self.extract_labeled_value(strings, "Date")
        time_text = self.extract_labeled_value(strings, "Time")
        location = self.extract_labeled_value(strings, "Location")

        if not title or not date_text:
            return None

        tz = ZoneInfo(self.timezone)
        today = datetime.now(tz).date()
        start_day, end_day = self.parse_date_range(date_text, today)
        if not start_day:
            return None

        parsed_times = self.parse_time_range(time_text) if time_text else None
        if parsed_times:
            (sh, sm), (eh, em) = parsed_times
            dtstart = datetime(start_day.year, start_day.month, start_day.day, sh, sm, tzinfo=tz)
            dtend = datetime(end_day.year, end_day.month, end_day.day, eh, em, tzinfo=tz)
        else:
            dtstart = start_day
            dtend = end_day

        return {
            "title": title,
            "dtstart": dtstart,
            "dtend": dtend,
            "url": url,
            "location": location,
            "description": description,
        }

    def fetch_events(self) -> list[dict]:
        events = []
        for url in self.fetch_event_urls():
            try:
                event = self.parse_event_page(url)
            except Exception as exc:
                self.logger.warning("Skipping %s: %s", url, exc)
                continue
            if event:
                events.append(event)
        return events


if __name__ == "__main__":
    WaterfrontBIAScraper.main()
