#!/usr/bin/env python3
"""Toronto Tool Library workshops from TTLmarket Shopify products."""

import html
import json
import logging
import re
import sys
from datetime import date, datetime, timedelta
from typing import Any
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

sys.path.insert(0, str(__file__).rsplit('/', 1)[0])

from lib.base import BaseScraper


LOGGER = logging.getLogger(__name__)
MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
TITLE_DATE_RE = re.compile(
    r"\b(?P<month>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
    r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)\s+"
    r"(?P<day>\d{1,2})(?:-(?P<end_day>\d{1,2}))?"
    r"(?:[,\s]+(?P<year>\d{4}))?\b",
    re.IGNORECASE,
)
TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.IGNORECASE)


def clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>|</h\d>|</li>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def parse_title_date(title: str, today: date) -> tuple[date, date | None] | tuple[None, None]:
    match = TITLE_DATE_RE.search(title)
    if not match:
        return None, None

    month = MONTHS[match.group("month").lower()]
    day = int(match.group("day"))
    end_day = int(match.group("end_day")) if match.group("end_day") else None
    year = int(match.group("year")) if match.group("year") else today.year

    try:
        start = date(year, month, day)
    except ValueError:
        return None, None

    if not match.group("year") and start < today - timedelta(days=7):
        start = date(year + 1, month, day)

    end = None
    if end_day:
        try:
            end = date(start.year, month, end_day)
        except ValueError:
            end = None
    return start, end


def parse_time_matches(page_text: str) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
    seen: list[tuple[int, int]] = []
    for hour_text, minute_text, meridian in TIME_RE.findall(page_text):
        hour = int(hour_text)
        minute = int(minute_text or "0")
        meridian = meridian.lower()
        if meridian == "pm" and hour != 12:
            hour += 12
        if meridian == "am" and hour == 12:
            hour = 0
        value = (hour, minute)
        if value not in seen:
            seen.append(value)
    if not seen:
        return None, None
    start = seen[0]
    end = seen[1] if len(seen) > 1 else None
    return start, end


class TorontoToolLibraryScraper(BaseScraper):
    name = "Toronto Tool Library"
    domain = "ttlmarket.com"
    timezone = "America/Toronto"
    base_url = "https://ttlmarket.com"
    default_location = "TTLMakerspace, 192 Spadina Ave., Toronto, ON"

    def fetch_json(self, url: str) -> Any:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read())

    def fetch_text(self, url: str) -> str:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", "ignore")

    def build_event(self, product: dict[str, Any], today: date) -> dict[str, Any] | None:
        start_date, end_date = parse_title_date(product.get("title", ""), today)
        if not start_date:
            LOGGER.debug("Skipping TTL product without parseable date: %s", product.get("title"))
            return None
        if start_date < today:
            return None

        page_url = f"{self.base_url}/products/{product.get('handle', '')}"
        page_text = self.fetch_text(page_url)
        body_text = clean_text(product.get("body_html", ""))
        start_time, end_time = parse_time_matches(page_text)

        if start_time:
            tz = ZoneInfo(self.timezone)
            dtstart = datetime(
                start_date.year,
                start_date.month,
                start_date.day,
                start_time[0],
                start_time[1],
                tzinfo=tz,
            )
            if end_time:
                dtend = datetime(
                    start_date.year,
                    start_date.month,
                    start_date.day,
                    end_time[0],
                    end_time[1],
                    tzinfo=tz,
                )
            else:
                dtend = dtstart + timedelta(hours=2)
        else:
            dtstart = start_date
            dtend = end_date + timedelta(days=1) if end_date else None

        return {
            "title": product.get("title", "").strip(),
            "dtstart": dtstart,
            "dtend": dtend,
            "location": self.default_location,
            "description": body_text,
            "url": page_url,
            "uid": f"ttl-{product['id']}@{self.domain}",
        }

    def fetch_events(self) -> list[dict[str, Any]]:
        now = datetime.now(ZoneInfo(self.timezone)).date()
        data = self.fetch_json(f"{self.base_url}/products.json?limit=250")
        events = []
        for product in data.get("products", []):
            if product.get("product_type") != "Event":
                continue
            event = self.build_event(product, now)
            if event:
                events.append(event)
        return events


if __name__ == "__main__":
    TorontoToolLibraryScraper.main()
