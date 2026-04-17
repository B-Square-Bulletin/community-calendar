#!/usr/bin/env python3
"""Bistitchual classes from Shopify products."""

import html
import json
import re
import sys
from datetime import date, datetime, timedelta
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

sys.path.insert(0, str(__file__).rsplit('/', 1)[0])

from lib.base import BaseScraper


MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
DATE_RE = re.compile(
    r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+"
    r"(?P<month>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
    r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)\s+"
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)?(?:,\s*(?P<year>\d{4}))?",
    re.IGNORECASE,
)
TIME_RANGE_RE = re.compile(
    r"from\s+(?P<start>\d{1,2}(?::\d{2})?(?:\s*(?:am|pm))?)\s*-\s*"
    r"(?P<end>\d{1,2}(?::\d{2})?\s*(?:am|pm))",
    re.IGNORECASE,
)


def clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>|</li>|</h\d>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_time(value: str, default_meridian: str | None = None) -> tuple[int, int]:
    match = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", value.strip(), re.IGNORECASE)
    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    meridian = (match.group(3) or default_meridian or "").lower()
    if meridian == "pm" and hour != 12:
        hour += 12
    if meridian == "am" and hour == 12:
        hour = 0
    return hour, minute


class BistitchualScraper(BaseScraper):
    name = "Bistitchual"
    domain = "bistitchual.ca"
    timezone = "America/Toronto"
    base_url = "https://bistitchual.ca"
    default_location = "Bistitchual, 266 Jane St, Toronto, ON M6S 3Z2"

    def fetch_events(self) -> list[dict]:
        request = Request(f"{self.base_url}/products.json?limit=250", headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=30) as response:
            data = json.loads(response.read())

        today = datetime.now(ZoneInfo(self.timezone)).date()
        events = []
        for product in data.get("products", []):
            tags = [tag.lower() for tag in product.get("tags", [])]
            if "classes" not in tags:
                continue

            text = clean_text(product.get("body_html", ""))
            date_match = DATE_RE.search(text)
            time_match = TIME_RANGE_RE.search(text)
            if not date_match:
                continue

            month = MONTHS[date_match.group("month").lower()]
            day = int(date_match.group("day"))
            year = int(date_match.group("year") or today.year)
            start_date = date(year, month, day)
            if start_date < today - timedelta(days=7):
                start_date = date(year + 1, month, day)
            if start_date < today:
                continue

            if time_match:
                end_meridian_match = re.search(r"(am|pm)", time_match.group("end"), re.IGNORECASE)
                end_meridian = end_meridian_match.group(1) if end_meridian_match else None
                start_hour, start_minute = parse_time(time_match.group("start"), end_meridian)
                end_hour, end_minute = parse_time(time_match.group("end"))
                tz = ZoneInfo(self.timezone)
                dtstart = datetime(start_date.year, start_date.month, start_date.day, start_hour, start_minute, tzinfo=tz)
                dtend = datetime(start_date.year, start_date.month, start_date.day, end_hour, end_minute, tzinfo=tz)
            else:
                dtstart = start_date
                dtend = None

            events.append({
                "title": product.get("title", "").strip(),
                "dtstart": dtstart,
                "dtend": dtend,
                "location": self.default_location,
                "description": text,
                "url": f"{self.base_url}/products/{product.get('handle', '')}",
                "uid": f"bistitchual-{product['id']}@{self.domain}",
            })
        return events


if __name__ == "__main__":
    BistitchualScraper.main()
